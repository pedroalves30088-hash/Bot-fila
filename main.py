import discord
from discord.ext import commands
import os
import random
import asyncio
from flask import Flask
from threading import Thread

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

# ===== COLOCA SUA CHAVE PIX AQUI =====
CHAVE_PIX_ADM = "COLOCA-SUA-CHAVE-PIX-AQUI"
NOME_ADM_PIX = "SEU NOME NO PIX"
# =====================================

VALORES = [0.05, 0.10, 0.15, 0.30, 0.60, 1, 2, 3, 5, 10, 20, 30, 50, 100]

def formatar_valor(v):
    if v < 1:
        return f"{v:.2f}cc".replace(".", ",")
    else:
        if v == int(v):
            return f"R$ {int(v)}"
        return f"R$ {v}"

filas = {}

def pegar_cargos_staff(guild):
    dono = mediador = None
    for r in guild.roles:
        nome = r.name.upper()
        if "DONO" in nome:
            dono = r
        if "MEDIADOR" in nome:
            mediador = r
    return dono, mediador

def tem_cargo_staff(member, guild):
    dono, mediador = pegar_cargos_staff(guild)
    ids = []
    if dono: ids.append(dono.id)
    if mediador: ids.append(mediador.id)
    return any(r.id in ids for r in member.roles)

# ===== BOTÕES CONFIRMAR / CANCELAR DENTRO DO AGUARDANDO =====
class BotoesConfirmar(discord.ui.View):
    def __init__(self, fila_info):
        super().__init__(timeout=None)
        self.fila = fila_info

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green, custom_id="confirmar")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Só DONO / MEDIADOR pode confirmar
        if not tem_cargo_staff(interaction.user, interaction.guild):
            await interaction.response.send_message("Só DONO / MEDIADOR pode confirmar!", ephemeral=True)
            return

        embed = discord.Embed(title="✅ PARTIDA CONFIRMADA!", color=0x00ff00)
        embed.add_field(name="Modo", value=f"{self.fila['modo']} | Full Ump Xm8", inline=False)
        embed.add_field(name="Valor", value=formatar_valor(self.fila['valor']), inline=False)
        embed.add_field(name="Jogadores", value=" x ".join([j.mention for j in self.fila['jogadores']]), inline=False)
        embed.add_field(name="🔑 CHAVE PIX DO ADM", value=f"**{CHAVE_PIX_ADM}**\nNome: {NOME_ADM_PIX}", inline=False)
        embed.add_field(name="📋 Como pagar", value=f"1. Paga **{formatar_valor(self.fila['valor'])}** pra chave acima\n2. Manda o comprovante aqui\n3. Chama o mediador pra criar a sala", inline=False)
        await interaction.response.send_message(embed=embed)
        # Desativa os botões depois de confirmar
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.red, custom_id="cancelar")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not tem_cargo_staff(interaction.user, interaction.guild):
            await interaction.response.send_message("Só DONO / MEDIADOR pode cancelar!", ephemeral=True)
            return
        await interaction.response.send_message("❌ Partida cancelada! Canal será apagado em 5 segundos...")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason="Partida cancelada")
        except:
            pass

# ===== BOTÕES DA FILA =====
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
        if len(fila["jogadores"]) >= 2:
            await interaction.response.send_message("Fila cheia!", ephemeral=True)
            return
        fila["jogadores"].append(user)
        await atualizar_painel(interaction, fila, self.msg_id)
        if len(fila["jogadores"]) == 2:
            await criar_canal_partida(interaction.guild, fila)
            fila["jogadores"] = []
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

async def criar_canal_partida(guild, fila):
    dono, mediador = pegar_cargos_staff(guild)
    numero = random.randint(10000, 99999)
    nome_canal = f"aguardando-{numero}"
    overwrites = { guild.default_role: discord.PermissionOverwrite(view_channel=False) }
    for j in fila["jogadores"]:
        overwrites[j] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    if dono:
        overwrites[dono] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    if mediador:
        overwrites[mediador] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    categoria = None
    for cat in guild.categories:
        if "MEDIADOR" in cat.name.upper() or "PARTIDA" in cat.name.upper():
            categoria = cat
            break

    canal = await guild.create_text_channel(nome_canal, overwrites=overwrites, category=categoria, reason=f"Partida {fila['modo']} {formatar_valor(fila['valor'])}")

    ping = ""
    if dono: ping += f"{dono.mention} "
    if mediador: ping += f"{mediador.mention} "

    jogadores = " x ".join([j.mention for j in fila["jogadores"]])
    embed = discord.Embed(title=f"Esperando Confirmar #{numero}", color=0xff0000)
    embed.add_field(name="Modo", value=f"{fila['modo']} | Full Ump Xm8", inline=False)
    embed.add_field(name="Valor", value=formatar_valor(fila["valor"]), inline=False)
    embed.add_field(name="Jogadores", value=jogadores, inline=False)
    # Aqui vai os botões Confirmar / Cancelar igual na Pocoyo
    await canal.send(content=f"{ping}Nova partida fechada!", embed=embed, view=BotoesConfirmar(fila))

@bot.command()
async def painel(ctx, modo: str = "2x2 Mobile"):
    try:
        await ctx.message.delete()
    except:
        pass
    for valor in reversed(VALORES):
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
