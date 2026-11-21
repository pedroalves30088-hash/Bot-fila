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

VALORES = [0.05, 0.10, 0.15, 0.30, 0.60, 1, 2, 3, 5, 10, 20, 30, 50, 100]

# TODOS OS MODOS JÁ PRONTOS
MODOS = ["1x1 Mobile", "2x2 Mobile", "3x3 Mobile", "4x4 Mobile", "2x2 Emu", "3x3 Emu", "4x4 Emu"]

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

# ===== BOTÕES CONFIRMAR / CANCELAR - OS 2 JOGADORES TEM QUE CONFIRMAR =====
class BotoesConfirmar(discord.ui.View):
    def __init__(self, fila_info):
        super().__init__(timeout=None)
        self.fila = fila_info
        self.confirmados = set()  # guarda quem já confirmou

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green, custom_id="confirmar")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Só quem tá na partida pode confirmar
        if interaction.user.id not in [j.id for j in self.fila["jogadores"]]:
            await interaction.response.send_message("Só os 2 jogadores da partida podem confirmar!", ephemeral=True)
            return

        if interaction.user.id in self.confirmados:
            await interaction.response.send_message("Você já confirmou! Esperando o outro jogador...", ephemeral=True)
            return

        self.confirmados.add(interaction.user.id)

        # FALTA 1 AINDA
        if len(self.confirmados) < 2:
            await interaction.response.send_message(f"✅ Você confirmou! **1/2** - Esperando o outro jogador confirmar...", ephemeral=False)
            return

        # OS 2 CONFIRMARAM
        embed = discord.Embed(title="✅ PARTIDA CONFIRMADA!", color=0x00ff00)
        embed.add_field(name="Modo", value=f"{self.fila['modo']} | Full Ump Xm8", inline=False)
        embed.add_field(name="Valor", value=formatar_valor(self.fila['valor']), inline=False)
        embed.add_field(name="Jogadores", value=" x ".join([j.mention for j in self.fila['jogadores']]), inline=False)
        embed.add_field(name="Próximo passo", value="Os 2 jogadores confirmaram! Aguardando ADM / MEDIADOR criar a sala.", inline=False)
        await interaction.response.send_message(embed=embed)
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.red, custom_id="cancelar")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Jogador da partida OU DONO / MEDIADOR pode cancelar
        e_jogador = interaction.user.id in [j.id for j in self.fila["jogadores"]]
        dono, mediador = pegar_cargos_staff(interaction.guild)
        ids_staff = []
        if dono: ids_staff.append(dono.id)
        if mediador: ids_staff.append(mediador.id)
        e_staff = any(r.id in ids_staff for r in interaction.user.roles)
        if not e_jogador and not e_staff:
            await interaction.response.send_message("Só os jogadores ou DONO/MEDIADOR podem cancelar!", ephemeral=True)
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
        # Trava por modo: 1x1 = 2 jogadores, 2x2 = 2, 3x3 = 2, 4x4 = 2 (é 2 times, não 8 pessoas)
        # Se quiser que 3x3 seja 6 pessoas, me fala!
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
    await canal.send(content=f"{ping}Nova partida fechada!", embed=embed, view=BotoesConfirmar(fila))

async def criar_paineis(ctx, modo):
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

# ===== COMANDOS PRONTOS - É SÓ DIGITAR NO CANAL CERTO =====
@bot.command()
async def painel(ctx, modo: str = "2x2 Mobile"):
    await criar_paineis(ctx, modo)

@bot.command()
async def painel1x1(ctx):
    await criar_paineis(ctx, "1x1 Mobile")

@bot.command()
async def painel2x2(ctx):
    await criar_paineis(ctx, "2x2 Mobile")

@bot.command()
async def painel3x3(ctx):
    await criar_paineis(ctx, "3x3 Mobile")

@bot.command()
async def painel4x4(ctx):
    await criar_paineis(ctx, "4x4 Mobile")

@bot.command()
async def painel2x2emu(ctx):
    await criar_paineis(ctx, "2x2 Emu")

@bot.command()
async def painel3x3emu(ctx):
    await criar_paineis(ctx, "3x3 Emu")

@bot.command()
async def painel4x4emu(ctx):
    await criar_paineis(ctx, "4x4 Emu")

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
