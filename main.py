import discord
from discord.ext import commands
import os
from threading import Thread
from flask import Flask

# --- SITE PRA MANTER O BOT ONLINE NO RENDER ---
app = Flask('')
@app.route('/')
def home():
    return "Bot Fila Online!"
def run():
    app.run(host='0.0.0.0', port=8080)
Thread(target=run, daemon=True).start()

# --- CONFIG DO BOT ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='!', intents=intents)

# VALORES IGUAL DO VIDEO: 0,05 ate 100
VALORES = [0.05, 0.15, 0.30, 0.50, 0.75, 1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 100]

# FILAS SALVAS: {id_da_mensagem: [lista de jogadores]}
filas = {}

def criar_embed(modo, valor, jogadores):
    embed = discord.Embed(title=f"{modo} | Apostado", color=0x2b2d31)
    embed.add_field(name="Modo:", value=modo, inline=False)
    embed.add_field(name="Valor:", value=f"R$ {valor:.2f}".replace(".", ","), inline=False)
    if len(jogadores) == 0:
        texto = "Nenhum jogador na fila"
    else:
        texto = "\n".join([f"{i+1}. {j}" for i, j in enumerate(jogadores)])
    embed.add_field(name="Jogadores:", value=texto, inline=False)
    embed.set_thumbnail(url="https://i.imgur.com/2Q8Z8Qe.png")
    return embed

class FilaView(discord.ui.View):
    def __init__(self, modo, valor):
        super().__init__(timeout=None)
        self.modo = modo
        self.valor = valor

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.success, emoji="✅")
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        key = str(interaction.message.id)
        lista = filas.get(key, [])
        nome = interaction.user.display_name
        if nome in lista:
            await interaction.response.send_message("Você já está na fila!", ephemeral=True)
            return
        lista.append(nome)
        filas[key] = lista
        await interaction.message.edit(embed=criar_embed(self.modo, self.valor, lista), view=self)
        await interaction.response.send_message(f"Você entrou na fila de R$ {self.valor}!", ephemeral=True)

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.danger, emoji="❌")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        key = str(interaction.message.id)
        lista = filas.get(key, [])
        nome = interaction.user.display_name
        if nome in lista:
            lista.remove(nome)
            filas[key] = lista
            await interaction.message.edit(embed=criar_embed(self.modo, self.valor, lista), view=self)
            await interaction.response.send_message("Você saiu da fila!", ephemeral=True)
        else:
            await interaction.response.send_message("Você não está na fila!", ephemeral=True)

    @discord.ui.button(label="Full", style=discord.ButtonStyle.secondary)
    async def full(self, interaction: discord.Interaction, button: discord.ui.Button):
        key = str(interaction.message.id)
        lista = filas.get(key, [])
        await interaction.response.send_message(f"Fila atual ({len(lista)}): {', '.join(lista) if lista else 'vazia'}", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Bot online como {bot.user}")

# COMANDO PRA CRIAR AS FILAS
# Exemplo no Discord: !painel 2x2 Mobile
# Ou: !painel 2x2 Misto
@bot.command()
async def painel(ctx, modo: str = "2x2", tipo: str = "Mobile"):
    nome_modo = f"{modo} {tipo}"
    await ctx.send(f"Criando filas de {nome_modo} de R$ 0,05 até R$ 100...")
    for valor in VALORES:
        embed = criar_embed(nome_modo, valor, [])
        view = FilaView(nome_modo, valor)
        msg = await ctx.send(embed=embed, view=view)
        filas[str(msg.id)] = []

# LIGA O BOT - TOKEN VEM DO RENDER
TOKEN = os.environ.get("DISCORD_TOKEN")
bot.run(TOKEN)
