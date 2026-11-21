import discord
from discord.ext import commands
import os
import random
import asyncio
import urllib.parse
import re
import json
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
intents.guilds = True
bot = commands.Bot(command_prefix=('!', '.'), intents=intents)

VALORES = [0.05, 0.10, 0.15, 0.30, 0.60, 1, 2, 3, 5, 10, 20, 30, 50, 100]
MAX_MEDIADORES_FILA = 2
CARGOS_PERMITIDOS = ["MEDIADOR", "DONO", "CEO", "SUP", "DEV"]
ARQUIVO_CHAVES = "chaves.json"
ARQUIVO_RANKING = "ranking.json"

def formatar_valor(v):
    if v < 1:
        return f"{v:.2f}cc".replace(".", ",")
    else:
        if v == int(v):
            return f"R$ {int(v)}"
        return f"R$ {v}"

filas = {}
ultimo_mediador_id = None
lista_mediadores = []
partidas_por_canal = {}

# ===== CHAVES =====
def carregar_chaves():
    try:
        if os.path.exists(ARQUIVO_CHAVES):
            with open(ARQUIVO_CHAVES, "r", encoding="utf-8") as f:
                dados = json.load(f)
                return {int(k): v for k, v in dados.items()}
    except Exception as e:
        print(f"Erro carregar chaves: {e}")
    return {}
def salvar_chaves():
    try:
        with open(ARQUIVO_CHAVES, "w", encoding="utf-8") as f:
            json.dump(chaves_mediadores, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro salvar chaves: {e}")
chaves_mediadores = carregar_chaves()
if chaves_mediadores:
    ultimo_mediador_id = list(chaves_mediadores.keys())[-1]

# ===== RANKING + COINS =====
def carregar_ranking():
    try:
        if os.path.exists(ARQUIVO_RANKING):
            with open(ARQUIVO_RANKING, "r", encoding="utf-8") as f:
                dados = json.load(f)
                return {int(k): v for k, v in dados.items()}
    except Exception as e:
        print(f"Erro carregar ranking: {e}")
    return {}
def salvar_ranking():
    try:
        with open(ARQUIVO_RANKING, "w", encoding="utf-8") as f:
            json.dump(ranking, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Erro salvar ranking: {e}")
ranking = carregar_ranking()

def pegar_perfil(user):
    if user.id not in ranking:
        ranking[user.id] = {"nome": user.display_name, "wins": 0, "losses": 0, "coins": 0, "partidas": 0}
    ranking[user.id]["nome"] = user.display_name
    return ranking[user.id]

def adicionar_vitoria(vencedor, perdedor):
    pv = pegar_perfil(vencedor)
    pp = pegar_perfil(perdedor)
    pv["wins"] += 1
    pv["coins"] += 1
    pv["partidas"] += 1
    pp["losses"] += 1
    pp["partidas"] += 1
    salvar_ranking()
    return pv, pp

def pegar_cargos_staff(guild):
    dono = mediador = None
    for r in guild.roles:
        nome = r.name.upper()
        if "DONO" in nome:
            dono = r
        if "MEDIADOR" in nome:
            mediador = r
    return dono, mediador
def tem_cargo_permitido(member, guild):
    if member.id == guild.owner_id:
        return True
    roles = getattr(member, "roles", [])
    for r in roles:
        nome = r.name.upper()
        for cargo in CARGOS_PERMITIDOS:
            if cargo in nome:
                return True
    return False
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
def gerar_pix(chave_pix, valor, nome="MEDIADOR", cidade="SAO PAULO"):
    chave_pix = chave_pix.strip()
    nome = nome.upper()[:25]
    cidade = cidade.upper()[:15]
    valor_str = f"{valor:.2f}"
    gui = campo("00", "BR.GOV.BCB.PIX") + campo("01", chave_pix)
    merchant = campo("26", gui)
    payload_sem_crc = "000201" + merchant + campo("52", "0000") + campo("53", "986") + campo("54", valor_str) + campo("58", "BR") + campo("59", nome) + campo("60", cidade) + campo("62", campo("05", "APOSTA")) + "6304"
    return payload_sem_crc + crc16(payload_sem_crc)
def gerar_qr_url(pix_copia_cola):
    dados = urllib.parse.quote(pix_copia_cola)
    return f"https://api.qrserver.com/v1/create-qr-code/?size=300x300&data={dados}"

class BotoesLiberarPix(discord.ui.View):
    def __init__(self, fila_info):
        super().__init__(timeout=None)
        self.fila = fila_info
    @discord.ui.button(label="Liberar Pix", style=discord.ButtonStyle.green, custom_id="liberar_pix")
    async def liberar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=False)
        med = self.fila.get("mediador_escolhido")
        if med and interaction.user.id != med.id and not tem_cargo_permitido(interaction.user, interaction.guild):
            await interaction.followup.send("❌ Só o mediador dessa partida pode liberar o Pix!", ephemeral=True)
            return
        chave_pix = None
        nome_med = "MEDIADOR"
        if med and med.id in chaves_mediadores:
            chave_pix = chaves_mediadores[med.id]["chave"]
            nome_med = chaves_mediadores[med.id]["nome"]
        elif interaction.user.id in chaves_mediadores:
            chave_pix = chaves_mediadores[interaction.user.id]["chave"]
            nome_med = chaves_mediadores[interaction.user.id]["nome"]
        elif ultimo_mediador_id and ultimo_mediador_id in chaves_mediadores:
            chave_pix = chaves_mediadores[ultimo_mediador_id]["chave"]
            nome_med = chaves_mediadores[ultimo_mediador_id]["nome"]
        elif chaves_mediadores:
            primeiro_id = list(chaves_mediadores.keys())[0]
            chave_pix = chaves_mediadores[primeiro_id]["chave"]
            nome_med = chaves_mediadores[primeiro_id]["nome"]
        if not chave_pix:
            await interaction.followup.send(f"⚠️ Mediador ainda não configurou a chave!\nDigita `!chave SUA-CHAVE-PIX`", ephemeral=False)
            return
        pix = gerar_pix(chave_pix, float(self.fila['valor']), nome=nome_med)
        qr_url = gerar_qr_url(pix)
        embed_qr = discord.Embed(title="💰 PAGAMENTO VIA PIX", color=0x00ff00)
        embed_qr.add_field(name="Valor a pagar", value=formatar_valor(self.fila['valor']), inline=False)
        embed_qr.add_field(name="Mediador", value=med.mention if med else nome_med, inline=False)
        embed_qr.add_field(name="Chave do Mediador", value=f"`{chave_pix}`", inline=False)
        embed_qr.add_field(name="Pix Copia e Cola", value=f"```{pix}```", inline=False)
        embed_qr.set_image(url=qr_url)
        await interaction.followup.send(embed=embed_qr)
        button.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass

class BotoesFilaMediadores(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    async def atualizar(self, interaction):
        lista = ""
        for i, m in enumerate(lista_mediadores):
            lista += f"{i+1}. {m.display_name}\n"
        if not lista:
            lista = "Nenhum mediador na fila"
        embed = discord.Embed(title="👤 Fila de Mediadores", color=0x5865F2)
        embed.add_field(name=f"{len(lista_mediadores)}/{MAX_MEDIADORES_FILA} mediador(es) na fila", value=lista, inline=False)
        if len(lista_mediadores) >= MAX_MEDIADORES_FILA:
            embed.add_field(name="🔒 Fila cheia", value="Um mediador precisa sair para abrir vaga.", inline=False)
        try:
            await interaction.message.edit(embed=embed, view=self)
        except Exception as e:
            print(f"Erro atualizar: {e}")
    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.blurple, custom_id="med_entrar")
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
        except:
            pass
        try:
            if not tem_cargo_permitido(interaction.user, interaction.guild):
                cargos = [r.name for r in getattr(interaction.user, "roles", [])]
                await interaction.followup.send(f"❌ Sem permissão! Cargos: {', '.join(cargos) if cargos else 'nenhum'}", ephemeral=True)
                return
            if any(m.id == interaction.user.id for m in lista_mediadores):
                await interaction.followup.send("Você já está na fila!", ephemeral=True)
                return
            if len(lista_mediadores) >= MAX_MEDIADORES_FILA:
                await interaction.followup.send("Fila cheia!", ephemeral=True)
                return
            lista_mediadores.append(interaction.user)
            await self.atualizar(interaction)
            await interaction.followup.send("✅ Você entrou na fila de mediadores!", ephemeral=True)
        except Exception as e:
            import traceback
            traceback.print_exc()
            try:
                await interaction.followup.send(f"Erro: {e}", ephemeral=True)
            except:
                pass
    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red, custom_id="med_sair")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
        except:
            pass
        lista_mediadores[:] = [m for m in lista_mediadores if m.id != interaction.user.id]
        await self.atualizar(interaction)
        try:
            await interaction.followup.send("Você saiu da fila!", ephemeral=True)
        except:
            pass
    @discord.ui.button(label="Limpar Fila", style=discord.ButtonStyle.red, custom_id="med_limpar")
    async def limpar(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
        except:
            pass
        lista_mediadores.clear()
        await self.atualizar(interaction)
        try:
            await interaction.followup.send("Fila limpa!", ephemeral=True)
        except:
            pass

class BotoesConfirmar(discord.ui.View):
    def __init__(self, fila_info):
        super().__init__(timeout=None)
        self.fila = fila_info
        self.confirmados = set()
    @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.green, custom_id="confirmar")
    async def confirmar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=False)
        if interaction.user.id in self.confirmados:
            await interaction.followup.send("Você já confirmou!", ephemeral=True)
            return
        self.confirmados.add(interaction.user.id)
        if len(self.confirmados) < 2:
            outro = [j for j in self.fila['jogadores'] if j.id != interaction.user.id]
            outro_txt = outro[0].mention if outro else "o outro jogador"
            embed = discord.Embed(title="Aposta Confirmada", color=0x5865F2)
            embed.add_field(name="", value=f"{interaction.user.mention} confirmou a aposta!\nAguardando {outro_txt} confirmar para iniciar.", inline=False)
            await interaction.followup.send(embed=embed)
            return
        canal = interaction.channel
        numero = self.fila.get("numero")
        if not numero:
            m = re.search(r"(\d+)", canal.name)
            numero = m.group(1) if m else random.randint(10000, 99999)
            self.fila["numero"] = numero
        try:
            await canal.edit(name=f"fila-{numero}")
        except Exception as e:
            print(f"Erro renomear: {e}")
        med = self.fila.get("mediador_escolhido")
        embed = discord.Embed(title="✅ Partida Confirmada", color=0x00ff00)
        embed.add_field(name="Modo", value=f"{self.fila['modo']} | Gelo Normal", inline=False)
        embed.add_field(name="Valor", value=formatar_valor(self.fila['valor']), inline=False)
        embed.add_field(name="Jogadores", value=" x ".join([j.mention for j in self.fila['jogadores']]), inline=False)
        if med:
            embed.add_field(name="Mediador", value=f"{med.mention}", inline=False)
            embed.add_field(name="No fim da partida, use .v ou .d então .aux", value=f"Aguarde o mediador {med.mention} liberar seu Pix", inline=False)
        await interaction.followup.send(embed=embed)
        if med:
            await canal.send(content=f"Aguarde o mediador {med.mention} liberar seu Pix", view=BotoesLiberarPix(self.fila))
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except:
            pass
    @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.red, custom_id="cancelar")
    async def cancelar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=False)
        await interaction.followup.send(f"❌ {interaction.user.mention} cancelou! Canal será apagado em 5 segundos...")
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete(reason="Partida cancelada")
        except:
            pass

class BotoesFila(discord.ui.View):
    def __init__(self, msg_id):
        super().__init__(timeout=None)
        self.msg_id = msg_id
    @discord.ui.button(label="Entrar", style=discord.ButtonStyle.green, custom_id="entrar")
    async def entrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        fila = filas.get(self.msg_id)
        if not fila:
            await interaction.followup.send("Essa fila não existe mais!", ephemeral=True)
            return
        user = interaction.user
        if user in fila["jogadores"]:
            await interaction.followup.send("Você já está na fila!", ephemeral=True)
            return
        if len(fila["jogadores"]) >= 2:
            await interaction.followup.send("Fila cheia!", ephemeral=True)
            return
        fila["jogadores"].append(user)
        await atualizar_painel(interaction, fila, self.msg_id)
        if len(fila["jogadores"]) == 2:
            jogadores_copia = list(fila["jogadores"])
            await criar_canal_partida(interaction.guild, fila, jogadores_copia)
            fila["jogadores"] = []
            await atualizar_painel(interaction, fila, self.msg_id)
    @discord.ui.button(label="Sair", style=discord.ButtonStyle.red, custom_id="sair")
    async def sair(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        fila = filas.get(self.msg_id)
        if fila and interaction.user in fila["jogadores"]:
            fila["jogadores"].remove(interaction.user)
            await atualizar_painel(interaction, fila, self.msg_id)
    @discord.ui.button(label="Full", style=discord.ButtonStyle.blurple, custom_id="full")
    async def full(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        fila = filas.get(self.msg_id)
        if not fila:
            return
        lista = "\n".join([f"{i+1}. {j.mention}" for i, j in enumerate(fila["jogadores"])]) or "Nenhum jogador ainda"
        await interaction.followup.send(f"**Fila {fila['modo']} - {formatar_valor(fila['valor'])}**\n{lista}", ephemeral=True)

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

async def criar_canal_partida(guild, fila_original, jogadores):
    fila = {"modo": fila_original["modo"], "valor": fila_original["valor"], "jogadores": list(jogadores), "numero": random.randint(10000, 99999), "resultado": None, "vencedor": None, "ranking_aplicado": False}
    dono, mediador_cargo = pegar_cargos_staff(guild)
    nome_canal = f"aguardando-{fila['numero']}"
    mediador_escolhido = None
    if lista_mediadores:
        mediador_escolhido = random.choice(lista_mediadores)
        fila["mediador_escolhido"] = mediador_escolhido
    else:
        fila["mediador_escolhido"] = None
    overwrites = { guild.default_role: discord.PermissionOverwrite(view_channel=False) }
    for j in fila["jogadores"]:
        overwrites[j] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    if dono:
        overwrites[dono] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    if mediador_cargo:
        overwrites[mediador_cargo] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    if mediador_escolhido:
        overwrites[mediador_escolhido] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
    categoria = None
    for cat in guild.categories:
        if "MEDIADOR" in cat.name.upper() or "PARTIDA" in cat.name.upper():
            categoria = cat
            break
    canal = await guild.create_text_channel(nome_canal, overwrites=overwrites, category=categoria, reason=f"Partida {fila['modo']} {formatar_valor(fila['valor'])}")
    partidas_por_canal[canal.id] = fila
    ping = ""
    if dono: ping += f"{dono.mention} "
    if mediador_cargo: ping += f"{mediador_cargo.mention} "
    jogadores_txt = " x ".join([j.mention for j in fila["jogadores"]])
    embed = discord.Embed(title=f"Esperando Confirmar #{fila['numero']}", color=0xff0000)
    embed.add_field(name="Modo", value=f"{fila['modo']} | Gelo Normal", inline=False)
    embed.add_field(name="Valor", value=formatar_valor(fila["valor"]), inline=False)
    embed.add_field(name="Jogadores", value=jogadores_txt, inline=False)
    if mediador_escolhido:
        embed.add_field(name="Mediador Sorteado", value=f"{mediador_escolhido.mention} - você vai mediar essa!", inline=False)
    else:
        embed.add_field(name="Mediador", value="Nenhum mediador na fila! Entra na `# fila-mediadores`", inline=False)
    await canal.send(content=f"{ping}Nova partida fechada!", embed=embed, view=BotoesConfirmar(fila))

# ===== .v .d .aux COM RANKING =====
@bot.command(name="v")
async def cmd_v(ctx, vencedor: discord.Member = None):
    fila = partidas_por_canal.get(ctx.channel.id)
    if not fila:
        await ctx.send("❌ Esse comando só funciona dentro do canal da partida!", delete_after=5)
        return
    if not tem_cargo_permitido(ctx.author, ctx.guild):
        await ctx.send("❌ Só o mediador / staff pode declarar o vencedor!", delete_after=5)
        return
    if not vencedor:
        await ctx.send("Uso: `.v @jogador`", delete_after=10)
        return
    if vencedor not in fila["jogadores"]:
        await ctx.send(f"❌ {vencedor.mention} não está nessa partida!", delete_after=5)
        return
    if fila.get("ranking_aplicado") and fila.get("vencedor"):
        antigo_v = fila["vencedor"]
        antigo_p = [j for j in fila["jogadores"] if j.id != antigo_v.id][0]
        if antigo_v.id in ranking:
            ranking[antigo_v.id]["wins"] = max(0, ranking[antigo_v.id]["wins"] - 1)
            ranking[antigo_v.id]["coins"] = max(0, ranking[antigo_v.id]["coins"] - 1)
            ranking[antigo_v.id]["partidas"] = max(0, ranking[antigo_v.id]["partidas"] - 1)
        if antigo_p.id in ranking:
            ranking[antigo_p.id]["losses"] = max(0, ranking[antigo_p.id]["losses"] - 1)
            ranking[antigo_p.id]["partidas"] = max(0, ranking[antigo_p.id]["partidas"] - 1)
    fila["resultado"] = "vitoria"
    fila["vencedor"] = vencedor
    perdedor = [j for j in fila["jogadores"] if j.id != vencedor.id][0]
    pv, pp = adicionar_vitoria(vencedor, perdedor)
    fila["ranking_aplicado"] = True
    embed = discord.Embed(title="🏆 Vitória Declarada!", color=0x00ff00)
    embed.add_field(name="Vencedor", value=f"{vencedor.mention}", inline=False)
    embed.add_field(name="Perdedor", value=f"{perdedor.mention}", inline=False)
    embed.add_field(name="Valor", value=formatar_valor(fila["valor"]), inline=False)
    embed.add_field(name="Recompensa", value=f"🪙 +1 Coin pro {vencedor.mention}!\nAgora ele tem **{pv['coins']} coins** e **{pv['wins']} wins**!", inline=False)
    embed.add_field(name="Próximo passo", value="Mediador, digita `.aux` pra finalizar e fechar o canal!", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="d")
async def cmd_d(ctx):
    fila = partidas_por_canal.get(ctx.channel.id)
    if not fila:
        await ctx.send("❌ Esse comando só funciona dentro do canal da partida!", delete_after=5)
        return
    if not tem_cargo_permitido(ctx.author, ctx.guild):
        await ctx.send("❌ Só o mediador / staff pode usar esse comando!", delete_after=5)
        return
    if fila.get("ranking_aplicado") and fila.get("vencedor"):
        antigo_v = fila["vencedor"]
        antigo_p = [j for j in fila["jogadores"] if j.id != antigo_v.id][0]
        if antigo_v.id in ranking:
            ranking[antigo_v.id]["wins"] = max(0, ranking[antigo_v.id]["wins"] - 1)
            ranking[antigo_v.id]["coins"] = max(0, ranking[antigo_v.id]["coins"] - 1)
            ranking[antigo_v.id]["partidas"] = max(0, ranking[antigo_v.id]["partidas"] - 1)
        if antigo_p.id in ranking:
            ranking[antigo_p.id]["losses"] = max(0, ranking[antigo_p.id]["losses"] - 1)
            ranking[antigo_p.id]["partidas"] = max(0, ranking[antigo_p.id]["partidas"] - 1)
        salvar_ranking()
    fila["resultado"] = "derrota"
    fila["vencedor"] = None
    fila["ranking_aplicado"] = False
    embed = discord.Embed(title="❌ Partida sem vencedor", color=0xff0000)
    embed.add_field(name="Jogadores", value=" x ".join([j.mention for j in fila["jogadores"]]), inline=False)
    embed.add_field(name="Valor", value=formatar_valor(fila["valor"]), inline=False)
    embed.add_field(name="Recompensa", value="Ninguém ganhou coin nessa!", inline=False)
    embed.add_field(name="Próximo passo", value="Mediador, digita `.aux` pra finalizar e fechar o canal!", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="aux")
async def cmd_aux(ctx):
    fila = partidas_por_canal.get(ctx.channel.id)
    if not fila:
        await ctx.send("❌ Esse comando só funciona dentro do canal da partida!", delete_after=5)
        return
    if not tem_cargo_permitido(ctx.author, ctx.guild):
        await ctx.send("❌ Só o mediador / staff pode finalizar!", delete_after=5)
        return
    if not fila.get("resultado"):
        await ctx.send("⚠️ Antes de `.aux` tu precisa usar `.v @vencedor` ou `.d`!", delete_after=10)
        return
    if fila["resultado"] == "vitoria":
        vencedor = fila["vencedor"]
        pv = pegar_perfil(vencedor)
        embed = discord.Embed(title="✅ Partida Finalizada!", color=0x00ff00)
        embed.add_field(name="🏆 Vencedor", value=f"{vencedor.mention}", inline=False)
        embed.add_field(name="Modo", value=f"{fila['modo']} | Gelo Normal", inline=False)
        embed.add_field(name="Valor", value=formatar_valor(fila["valor"]), inline=False)
        embed.add_field(name="Histórico do Vencedor", value=f"🏆 {pv['wins']} Wins | ❌ {pv['losses']} Losses | 🪙 {pv['coins']} Coins", inline=False)
        embed.add_field(name="Mediador", value=f"{ctx.author.mention} finalizou", inline=False)
        await ctx.send(embed=embed)
    else:
        embed = discord.Embed(title="✅ Partida Finalizada - Sem Vencedor", color=0xffaa00)
        embed.add_field(name="Jogadores", value=" x ".join([j.mention for j in fila["jogadores"]]), inline=False)
        embed.add_field(name="Valor", value=formatar_valor(fila["valor"]), inline=False)
        await ctx.send(embed=embed)
    await ctx.send("🔒 Canal será apagado em 10 segundos...")
    await asyncio.sleep(10)
    try:
        del partidas_por_canal[ctx.channel.id]
    except:
        pass
    try:
        await ctx.channel.delete(reason="Partida finalizada com .aux")
    except:
        pass

# ===== RANKING - !ranking / !r =====
@bot.command(name="ranking", aliases=["r"])
async def cmd_ranking(ctx):
    if not ranking:
        await ctx.send("📊 Ninguém jogou ainda! Seja o primeiro a ganhar uma coin!")
        return
    ordenado = sorted(ranking.items(), key=lambda x: (x[1]["wins"], x[1]["coins"]), reverse=True)[:10]
    texto = ""
    medalhas = ["🥇", "🥈", "🥉"]
    for i, (uid, dados) in enumerate(ordenado):
        medalha = medalhas[i] if i < 3 else f"{i+1}."
        winrate = 0
        if dados["partidas"] > 0:
            winrate = int(dados["wins"] / dados["partidas"] * 100)
        texto += f"{medalha} **{dados['nome']}** - 🏆 {dados['wins']}W | ❌ {dados['losses']}L | 🪙 {dados['coins']} coins | {winrate}% WR\n"
    embed = discord.Embed(title="🏆 RANKING - TOP 10", color=0xffd700)
    embed.add_field(name="Classificação por Wins", value=texto, inline=False)
    embed.set_footer(text="Use !p @pessoa pra ver o perfil completo")
    await ctx.send(embed=embed)

# ===== PERFIL - !perfil / !p =====
@bot.command(name="perfil", aliases=["p"])
async def cmd_perfil(ctx, membro: discord.Member = None):
    alvo = membro or ctx.author
    dados = pegar_perfil(alvo)
    salvar_ranking()
    winrate = 0
    if dados["partidas"] > 0:
        winrate = int(dados["wins"] / dados["partidas"] * 100)
    embed = discord.Embed(title=f"📊 Perfil de {alvo.display_name}", color=0x5865F2)
    embed.set_thumbnail(url=alvo.display_avatar.url if alvo.display_avatar else None)
    embed.add_field(name="🏆 Wins", value=str(dados["wins"]), inline=True)
    embed.add_field(name="❌ Losses", value=str(dados["losses"]), inline=True)
    embed.add_field(name="🪙 Coins", value=str(dados["coins"]), inline=True)
    embed.add_field(name="🎮 Partidas", value=str(dados["partidas"]), inline=True)
    embed.add_field(name="📈 Win Rate", value=f"{winrate}%", inline=True)
    await ctx.send(embed=embed)

@bot.command(name="coins")
async def cmd_coins(ctx, membro: discord.Member = None):
    alvo = membro or ctx.author
    dados = pegar_perfil(alvo)
    salvar_ranking()
    await ctx.send(f"🪙 {alvo.mention} tem **{dados['coins']} coins** | 🏆 {dados['wins']} wins | ❌ {dados['losses']} losses")

@bot.command(name="addcoin")
async def cmd_addcoin(ctx, membro: discord.Member = None, qtd: int = 1):
    if not tem_cargo_permitido(ctx.author, ctx.guild):
        await ctx.send("❌ Só staff pode dar coin!", delete_after=5)
        return
    if not membro:
        await ctx.send("Uso: `!addcoin @pessoa 5`", delete_after=5)
        return
    dados = pegar_perfil(membro)
    dados["coins"] += qtd
    salvar_ranking()
    await ctx.send(f"✅ {membro.mention} ganhou +{qtd} coins! Agora tem {dados['coins']} coins! 🪙")

@bot.command(name="removecoin")
async def cmd_removecoin(ctx, membro: discord.Member = None, qtd: int = 1):
    if not tem_cargo_permitido(ctx.author, ctx.guild):
        await ctx.send("❌ Só staff pode tirar coin!", delete_after=5)
        return
    if not membro:
        await ctx.send("Uso: `!removecoin @pessoa 1`", delete_after=5)
        return
    dados = pegar_perfil(membro)
    dados["coins"] = max(0, dados["coins"] - qtd)
    salvar_ranking()
    await ctx.send(f"✅ {membro.mention} perdeu -{qtd} coins! Agora tem {dados['coins']} coins!")

@bot.command(name="resetranking")
async def cmd_resetranking(ctx):
    if ctx.author.id != ctx.guild.owner_id and not tem_cargo_permitido(ctx.author, ctx.guild):
        await ctx.send("❌ Só staff pode resetar!", delete_after=5)
        return
    ranking.clear()
    salvar_ranking()
    await ctx.send("🧹 Ranking resetado!")

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

@bot.command(name="fila_mediadores")
async def cmd_fila_mediadores(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    embed = discord.Embed(title="👤 Fila de Mediadores", color=0x5865F2)
    embed.add_field(name=f"0/{MAX_MEDIADORES_FILA} mediador(es) na fila", value="Nenhum mediador na fila", inline=False)
    await ctx.send(embed=embed, view=BotoesFilaMediadores())

@bot.command(name="chave")
async def cmd_chave(ctx, *, nova_chave: str = None):
    if not tem_cargo_permitido(ctx.author, ctx.guild):
        await ctx.send("❌ Só MEDIADOR / DONO / CEO / SUP / DEV pode configurar!", delete_after=5)
        return
    if not nova_chave:
        await ctx.send("Uso: `!chave SUA-CHAVE-PIX`", delete_after=10)
        return
    nova_chave = nova_chave.strip()
    global ultimo_mediador_id
    chaves_mediadores[ctx.author.id] = {"chave": nova_chave, "nome": ctx.author.display_name}
    ultimo_mediador_id = ctx.author.id
    salvar_chaves()
    try:
        await ctx.message.delete()
    except:
        pass
    await ctx.send(f"✅ {ctx.author.mention} sua chave PIX foi salva!\nChave: `{nova_chave}`", delete_after=15)

@bot.command(name="minhachave")
async def cmd_minhachave(ctx):
    if ctx.author.id in chaves_mediadores:
        dados = chaves_mediadores[ctx.author.id]
        await ctx.send(f"✅ {ctx.author.mention} tua chave tá salva!\nChave: `{dados['chave']}`", delete_after=15)
    else:
        await ctx.send(f"❌ {ctx.author.mention} tu ainda NÃO tem chave salva!\nDigita: `!chave SUA-CHAVE-PIX`", delete_after=10)
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
    print(f"Chaves: {len(chaves_mediadores)} | Ranking: {len(ranking)} jogadores")
    bot.add_view(BotoesFilaMediadores())

bot.run(os.getenv("DISCORD_TOKEN"))
