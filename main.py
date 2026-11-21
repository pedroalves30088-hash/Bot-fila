import discord
from discord.ext import commands
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

# VALORES DO MENOR PRO MAIOR - NÃO MEXER NA ORDEM
VALORES = [0.05, 0.15, 0.30, 0.50, 1, 2, 2.5, 3, 5, 10, 20, 30, 50, 90, 100]

# Fila: valor -> lista de jogadores
filas = {v: [] for v in VALORES}

# Cargos que podem ver a aposta
CARGOS_STAFF = ["MEDIADOR", "FILAS ADM", "DONO", "CEO", "DIRETOR", "DEV"]

def formatar_valor(v):
    if v == 0.05:
        return "R$ 0,05"
    if v == 0.15:
        return "R$ 0,15"
    if v == 0.30:
        return "R$ 0,30"
    if v == 0.50:
        return "R$ 0,50"
    if v == 2.5:
        return "R$ 2,50"
    # resto inteiro
    return f"R$ {int(v)},00" if v == int(v) else f"R$ {str(v).replace('.', ',')}"

class PainelView(discord.ui.View):
    def __init__(self, valor):
        super().__init__(timeout=None)
        self.valor = valor

    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green, custom_id="entrar")
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        valor = self.valor
        user = interaction.user
        guild = interaction.guild

        if user.id in filas[valor]:
            await interaction.response.send_message("Você já está na fila!", ephemeral=True)
            return

        filas[valor].append(user.id)
        await interaction.response.send_message(f"Você entrou na fila de {formatar_valor(valor)}! ({len(filas[valor])}/2)", ephemeral=True)

        # QUANDO FECHAR 2 JOGADORES -> VAI PRA APOSTAS
        if len(filas[valor]) == 2:
            jogador1 = guild.get_member(filas[valor][0])
            jogador2 = guild.get_member(filas[valor][1])

            # Acha a categoria APOSTAS
            categoria = None
            for cat in guild.categories:
                if "APOSTAS" in cat.name.upper():
                    categoria = cat
                    break

            # Permissões do canal privado
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
                jogador1: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                jogador2: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            }

            # Libera os cargos da staff
            for nome_cargo in CARGOS_STAFF:
                cargo = discord.utils.get(guild.roles, name=nome_cargo)
                if cargo:
                    overwrites[cargo] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

            nome_canal = f"aposta-{str(valor).replace('.', '-')}-{jogador1.name}-x-{jogador2.name}".lower()[:90]
            novo_canal = await guild.create_text_channel(nome_canal, category=categoria, overwrites=overwrites)

            cargo_mediador = discord.utils.get(guild.roles, name="MEDIADOR")
            mencao_mediador = cargo_mediador.mention if cargo_mediador else "@MEDIADOR"

            embed = discord.Embed(
                title=f"⚔️ APOSTA {formatar_valor(valor)} - 2x2 Mobile",
                description=f"{jogador1.mention} 🆚 {jogador2.mention}\n\n{mencao_mediador} - Assume a mediação!",
                color=discord.Color.gold()
            )
            embed.add_field(name="Jogador 1", value=jogador1.mention, inline=True)
            embed.add_field(name="Jogador 2", value=jogador2.mention, inline=True)
            embed.add_field(name="Valor", value=formatar_valor(valor), inline=False)
            embed.set_footer(text="Boa sorte! Chame um mediador para começar.")

            await novo_canal.send(content=f"{jogador1.mention} {jogador2.mention} {mencao_mediador}", embed=embed)

            # Limpa a fila desse valor
            filas[valor] = []

    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red, custom_id="sair")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        valor = self.valor
        if interaction.user.id in filas[valor]:
            filas[valor].remove(interaction.user.id)
            await interaction.response.send_message("Você saiu da fila!", ephemeral=True)
        else:
            await interaction.response.send_message("Você não está na fila!", ephemeral=True)

    @discord.ui.button(label="Full", style=discord.ButtonStyle.blurple, custom_id="full")
    async def full(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"Fila de {formatar_valor(self.valor)}: {len(filas[self.valor])}/2", ephemeral=True)

@bot.command()
async def painel(ctx, *args):
    # !painel 2x2 Mobile
    titulo = " ".join(args) if args else "2x2 Mobile"
    # Apaga o comando
    try:
        await ctx.message.delete()
    except:
        pass

    # Manda SEMPRE do menor pro maior
    for valor in sorted(VALORES):
        embed = discord.Embed(
            title=f"🎮 {titulo} | {formatar_valor(valor)}",
            description=f"Valor: **{formatar_valor(valor)}**\nClique em Entrar para entrar na fila!",
            color=discord.Color.green()
        )
        embed.set_footer(text="2 jogadores = cria aposta privada automaticamente")
        await ctx.send(embed=embed, view=PainelView(valor))

@bot.command()
async def clear_all(ctx):
    await ctx.channel.purge(limit=100)
    await ctx.send("✅ Canal limpo!", delete_after=3)

@bot.event
async def on_ready():
    print(f"Bot online: {bot.user}")

bot.run(os.getenv("DISCORD_TOKEN"))
