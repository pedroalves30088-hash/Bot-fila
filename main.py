import discord
from discord.ext import commands
import os
from flask import Flask
from threading import Thread

# --- KEEP ALIVE PRO RENDER NÃO DORMIR ---
app = Flask('')
@app.route('/')
def home():
    return "Bot online!"
def run():
    app.run(host='0.0.0.0', port=8080)
Thread(target=run, daemon=True).start()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# LISTA DE VALORES - COMEÇA DE 0.05 E VAI ATÉ 100
VALORES = [0.05, 0.10, 0.15, 0.30, 0.60, 1, 2, 3, 5, 10, 20, 30, 50, 100]

def formatar_valor(v):
    if v < 1:
        return f"{v:.2f}cc".replace(".", ",")
    else:
        if v == int(v):
            return f"R$ {int(v)}"
        return f"R$ {v}"

# Guarda as filas: {id_da_mensagem: {"modo": "2x2 Mobile", "valor": 1, "jogadores": []}}
filas = {}

class BotoesFila(discord.ui.View):
    def __init__(self, msg_id):
        super().__init__(timeout=None)
        self.msg_id = msg_id

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green, custom_id="entrar")
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        fila = filas.get(self.msg_id)
        if not fila:
            await interaction.response.send_message("Essa fila não existe mais!", ephemeral=True)
            return

        user = interaction.user
        if user in fila["jogadores"]:
            await interaction.response.send_message("Você já está na fila!", ephemeral=True)
            return

        # 2x2 = máximo 2 jogadores
        if len(fila["jogadores"]) >= 2:
            await interaction.response.send_message("Fila cheia!", ephemeral=True)
            return

        fila["jogadores"].append(user)
        await atualizar_painel(interaction, fila, self.msg_id)

        # QUANDO ENCHER 2 JOGADORES -> MANDA PRA #apostas
        if len(fila["jogadores"]) == 2:
            await enviar_para_apostas(interaction.guild, fila)
            fila["jogadores"] = []  # zera a fila pra próxima dupla
            await atualizar_painel(interaction, fila, self.msg_id)

        await interaction.response.defer()

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red, custom_id="sair")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        fila = filas.get(self.msg_id)
        if fila and interaction.user in fila["jogadores"]:
            fila["jogadores"].remove(interaction.user)
            await atualizar_painel(interaction, fila, self.msg_id)
        await interaction.response.defer()

    @discord.ui.button(label="Full", style=discord.ButtonStyle.blurple, custom_id="full")
    async def full(self, interaction: discord.Interaction, button: discord.ui.Button):
        fila = filas.get(self.msg_id)
        if not fila:
            return
        lista = "\n".join([f"{i+1}. {j.mention}" for i, j in enumerate(fila["jogadores"])]) or "Nenhum jogador ainda"
        await interaction.response.send_message(f"**Fila {fila['modo']} - {formatar_valor(fila['valor'])}**\n{lista}", ephemeral=True)

async def atualizar_painel(interaction, fila, msg_id):
    try:
        msg = await interaction.channel.fetch_message(msg_id)
        jogadores_txt = "\n".join([f"{i+1}. {j.display_name}" for i, j in enumerate(fila["jogadores"])]) or "Nenhum jogador ainda"
        embed = discord.Embed(title=f"{fila['modo']} | Apostado", color=0x00ff00)
        embed.add_field(name="Modo", value=fila["modo"], inline=False)
        embed.add_field(name="Valor", value=formatar_valor(fila["valor"]), inline=False)
        embed.add_field(name="Jogadores:", value=jogadores_txt, inline=False)
        await msg.edit(embed=embed, view=BotoesFila(msg_id))
    except:
        pass

async def enviar_para_apostas(guild, fila):
    # Acha o canal de apostas pelo nome
    canal_apostas = discord.utils.get(guild.text_channels, name="apostas")
    if not canal_apostas:
        for c in guild.text_channels:
            if "apostas" in c.name.lower():
                canal_apostas = c
                break
    if not canal_apostas:
        return

    # TRAVA O CANAL: só DONO e MEDIADOR veem
    # CORRIGIDO: procura pelo nome mesmo com emoji 👑 • DONO
    try:
        dono = None
        mediador = None
        for r in guild.roles:
            nome = r.name.upper()
            if "DONO" in nome:
                dono = r
            if "MEDIADOR" in nome:
                mediador = r

        # @everyone não vê
        await canal_apostas.set_permissions(guild.default_role, view_channel=False)
        if dono:
            await canal_apostas.set_permissions(dono, view_channel=True, send_messages=True, read_message_history=True)
        if mediador:
            await canal_apostas.set_permissions(mediador, view_channel=True, send_messages=True, read_message_history=True)
    except Exception as e:
        print(f"Erro ao travar canal: {e}")

    jogadores = " x ".join([j.mention for j in fila["jogadores"]])
    embed = discord.Embed(title="🔥 NOVA APOSTA FECHADA!", color=0xff0000)
    embed.add_field(name="Modo", value=fila["modo"], inline=False)
    embed.add_field(name="Valor", value=formatar_valor(fila["valor"]), inline=False)
    embed.add_field(name="Dupla", value=jogadores, inline=False)
    await canal_apostas.send(embed=embed)

@bot.command()
async def painel(ctx, modo: str = "2x2 Mobile"):
    try:
        await ctx.message.delete()
    except:
        pass

    for valor in VALORES:
        embed = discord.Embed(title=f"{modo} | Apostado", color=0x00ff00)
        embed.add_field(name="Modo", value=modo, inline=False)
        embed.add_field(name="Valor", value=formatar_valor(valor), inline=False)
        embed.add_field(name="Jogadores:", value="Nenhum jogador ainda", inline=False)
        msg = await ctx.send(embed=embed, view=BotoesFila(0))
        filas[msg.id] = {"modo": modo, "valor": valor, "jogadores": []}
        await msg.edit(view=BotoesFila(msg.id))

@bot.command()
async def clear_all(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    filas.clear()
    deleted = await ctx.channel.purge(limit=100)
    await ctx.send(f"🧹 Limpado {len(deleted)} mensagens!", delete_after=5)

@bot.event
async def on_ready():
    print(f"Bot logado como {bot.user}")

bot.run(os.getenv("DISCORD_TOKEN"))
