import discord
from discord.ext import commands
import os
import random
import asyncio
import urllib.parse
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

def formatar_valor(v):
    if v < 1:
        return f"{v:.2f}cc".replace(".", ",")
    else:
        if v == int(v):
            return f"R$ {int(v)}"
        return f"R$ {v}"

filas = {}

# ===== SALVA AS CHAVES DOS MEDIADORES =====
# { id_do_mediador: {"chave": "...", "nome": "Nome"} }
chaves_mediadores = {}
ultimo_mediador_id = None

def pegar_cargos_staff(guild):
    dono = mediador = None
    for r in guild.roles:
        nome = r.name.upper()
        if "DONO" in nome:
            dono = r
        if "MEDIADOR" in nome:
            mediador = r
    return dono, mediador

# ===== GERA PIX COPIA E COLA COM VALOR =====
def crc16(payload):
    crc = 0xFFFF
    for b in payload.encode():
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"

def campo(id, valor):
    return f"{id}{len(valor):02d}{valor}"

def gerar_pix(chave, valor, nome="MEDIADOR", cidade="SAO PAULO"):
    # Remove espaços da chave
    chave = chave.strip()
    nome = nome.upper()[:25]
    cidade = cidade.upper()[:15]
    valor_str = f"{valor:.2f}"
    gui = campo("00", "BR.GOV.BCB.PIX") + campo("01", chave)
    merchant = campo("26", gui)
    payload_sem_crc = "000201" + merchant + campo("52", "0000") + campo("53", "986") + campo("54", valor_str) + campo("58", "BR") + campo("59", nome) + campo("60", cidade) + campo("62", campo("05", "APOSTA")) + "6304"
    return payload_sem_crc + crc16(payload_sem_crc)

def gerar_qr_url(pix_copia_cola):
    # Usa API grátis pra gerar QR, sem precisar instalar nada no Render
    dados = urllib.parse.quote(pix_copia_cola)
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={dados}"

# ===== CONFIRMAR / CANCELAR =====
class BotoesConfirmar(discord.ui.View):
    def __init__(self, fila_info):
        super().__init__(timeout=None)
        self.fila = fila_info
        self.confirmados = set()

    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green, custom_id="confirmar")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.confirmados:
            await interaction.response.send_message("Você já confirmou! Esperando mais 1 pessoa...", ephemeral=True)
            return
        self.confirmados.add(interaction.user.id)
        if len(self.confirmados) < 2:
            await interaction.response.send_message(f"✅ {interaction.user.mention} confirmou! **1/2** - Falta mais 1 pessoa confirmar...", ephemeral=False)
            return

        # 2 CONFIRMARAM - MANDA O QR CODE
        embed = discord.Embed(title="✅ PARTIDA CONFIRMADA!", color=0x00ff00)
        embed.add_field(name="Modo", value=f"{self.fila['modo']} | Full Ump Xm8", inline=False)
        embed.add_field(name="Valor", value=formatar_valor(self.fila['valor']), inline=False)
        embed.add_field(name="Jogadores", value=" x ".join([j.mention for j in self.fila['jogadores']]), inline=False)
        await interaction.response.send_message(embed=embed)

        # Tenta pegar a chave do mediador que configurou
        global ultimo_mediador_id
        mediador_id = ultimo_mediador_id
        # Se o mediador da partida for um dos que configurou, usa ele
        for j in self.fila.get("mediadores_da_partida", []):
            if j.id in chaves_mediadores:
                mediador_id = j.id
                break

        if mediador_id and mediador_id in chaves_mediadores:
            info = chaves_mediadores[mediador_id]
            chave = info["chave"]
            nome = info["nome"]
            pix = gerar_pix(chave, float(self.fila['valor']), nome=nome)
            qr_url = gerar_qr_url(pix)
            embed_qr = discord.Embed(title="💰 PAGAMENTO VIA PIX", color=0x00ff00)
            embed_qr.add_field(name="Valor a pagar", value=formatar_valor(self.fila['valor']), inline=False)
            embed_qr.add_field(name="Chave do Mediador", value=f"`{chave}`", inline=False)
            embed_qr.add_field(name="Pix Copia e Cola", value=f"```{pix}```", inline=False)
            embed_qr.add_field(name="Como pagar", value="1. Escaneia o QR Code abaixo\n2. Ou copia o código acima\n3. Manda o comprovante aqui e aguarda o mediador liberar", inline=False)
            embed_qr.set_image(url=qr_url)
            await interaction.channel.send(embed=embed_qr)
        else:
            await interaction.channel.send("⚠️ Nenhum mediador configurou a chave ainda! Mediador, vai no canal `# 🔑 • configurar-chave` e digita `!chave SUA-CHAVE`")

        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass

    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.red, custom_id="cancelar")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"❌ {interaction.user.mention} cancelou a partida! Canal será apagado em 5 segundos...")
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

# ===== CONFIGURAR CHAVE - SÓ NO CANAL configurar-chave =====
@bot.command()
async def chave(ctx, nova_chave: str = None):
    # Só deixa usar no canal configurar-chave ou por DONO/MEDIADOR
    if "configurar-chave" not in ctx.channel.name.lower() and "configurar" not in ctx.channel.name.lower():
        await ctx.send("❌ Use esse comando só no canal `# 🔑 • configurar-chave`!", delete_after=5)
        return
    dono, mediador = pegar_cargos_staff(ctx.guild)
    ids_staff = []
    if dono: ids_staff.append(dono.id)
    if mediador: ids_staff.append(mediador.id)
    e_staff = any(r.id in ids_staff for r in ctx.author.roles)
    if not e_staff and ctx.author.id != ctx.guild.owner_id:
        await ctx.send("❌ Só DONO / MEDIADOR pode configurar a chave!", delete_after=5)
        return
    if not nova_chave:
        await ctx.send("Uso: `!chave SUA-CHAVE-PIX`\nEx: `!chave 11999999999` ou `!chave meuemail@gmail.com`", delete_after=10)
        return
    global ultimo_mediador_id
    chaves_mediadores[ctx.author.id] = {"chave": nova_chave, "nome": ctx.author.display_name}
    ultimo_mediador_id = ctx.author.id
    try:
        await ctx.message.delete()
    except:
        pass
    await ctx.send(f"✅ {ctx.author.mention} sua chave PIX foi salva!\nChave: `{nova_chave}`\nAgora quando puxarem fila, o QR Code vai ser gerado com essa chave.", delete_after=10)

@bot.command()
async def ver_chave(ctx):
    if ctx.author.id in chaves_mediadores:
        info = chaves_mediadores[ctx.author.id]
        await ctx.send(f"Sua chave atual: `{info['chave']}`", delete_after=10)
    else:
        await ctx.send("Você ainda não configurou! Use `!chave SUA-CHAVE`", delete_after=10)
    try:
        await ctx.message.delete()
    except:
        pass

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
