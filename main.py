import discord
from discord.ext import commands
import sqlite3
import datetime
import os
from threading import Thread
from flask import Flask
import asyncio

# ————— KEEP-ALIVE FLASK (Replit 24/7) —————
app = Flask(__name__)
@app.route('/')
def home():
    return "Bank-Life-Bot-24-24 – En ligne 24/7 !", 200
def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
Thread(target=run_flask, daemon=True).start()

# ————— CONFIG —————
PREFIX = "!"
ADMIN_ROLE_NAME = "Banquier"

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

DB_NAME = "banque.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS comptes (user_id INTEGER PRIMARY KEY, solde INTEGER DEFAULT 20000)''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                 id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, type TEXT,
                 auteur_id INTEGER, cible_id INTEGER, montant INTEGER,
                 solde_avant INTEGER, solde_apres INTEGER, commentaire TEXT)''')
    conn.commit(); conn.close()

def get_solde(user_id):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("SELECT solde FROM comptes WHERE user_id = ?", (user_id,))
    row = c.fetchone(); conn.close()
    return row[0] if row else None

def creer_compte(user_id):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO comptes (user_id, solde) VALUES (?, 20000)", (user_id,))
    conn.commit(); conn.close()

def update_solde(user_id, nouveau_solde):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO comptes (user_id, solde) VALUES (?, ?)", (user_id, nouveau_solde))
    conn.commit(); conn.close()

def log_transaction(type_transac, auteur_id, cible_id, montant, solde_avant, solde_apres, commentaire=""):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""INSERT INTO transactions
                 (timestamp, type, auteur_id, cible_id, montant, solde_avant, solde_apres, commentaire)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
              (now, type_transac, auteur_id, cible_id, montant, solde_avant, solde_apres, commentaire))
    conn.commit(); conn.close()

@bot.event
async def on_ready():
    init_db()
    print(f"✅ {bot.user} est en ligne – Bank-Life-Bot 24/7 prêt !")

def is_admin(ctx):
    return any(role.name == ADMIN_ROLE_NAME for role in ctx.author.roles)

async def send_log_embed(dest, embed):
    try: await dest.send(embed=embed)
    except: pass

@bot.command(name="solde")
async def solde(ctx):
    creer_compte(ctx.author.id)
    s = get_solde(ctx.author.id)
    embed = discord.Embed(title="Votre compte Life-Bank", color=0x00ff00)
    embed.add_field(name="Titulaire", value=ctx.author.display_name, inline=False)
    embed.add_field(name="Solde", value=f"**{s:,} €**".replace(",", " "), inline=False)
    await ctx.send(embed=embed, delete_after=15); await ctx.message.delete()

@bot.command(name="virement")
async def virement(ctx, membre: discord.Member, montant: int):
    if montant <= 0: return await ctx.send("Le montant doit être positif.")
    if membre.bot or membre == ctx.author: return await ctx.send("Opération impossible.")
    creer_compte(ctx.author.id); creer_compte(membre.id)
    s = get_solde(ctx.author.id)
    if s < montant: return await ctx.send(f"Fonds insuffisants ({s:,} €).")
    update_solde(ctx.author.id, s - montant)
    log_transaction("Virement envoyé", ctx.author.id, membre.id, montant, s, s-montant, f"Vers {membre}")
    update_solde(membre.id, get_solde(membre.id) + montant)
    log_transaction("Virement reçu", ctx.author.id, membre.id, montant, get_solde(membre.id)-montant, get_solde(membre.id), f"De {ctx.author}")
    embed = discord.Embed(title="Virement effectué", color=0x00ff00)
    embed.add_field(name="De → À", value=f"{ctx.author.mention} → {membre.mention}", inline=False)
    embed.add_field(name="Montant", value=f"**{montant:,} €**".replace(",", " "), inline=False)
    embed.add_field(name="Nouveau solde", value=f"**{s-montant:,} €**".replace(",", " "), inline=False)
    await ctx.send(embed=embed)

@bot.command(name="add")
@commands.check(lambda ctx: is_admin(ctx))
async def add_money(ctx, membre: discord.Member, montant: int):
    if montant <= 0: return await ctx.send("Montant positif.")
    creer_compte(membre.id)
    ancien = get_solde(membre.id)
    update_solde(membre.id, ancien + montant)
    log_transaction("Admin +", ctx.author.id, membre.id, montant, ancien, ancien+montant, "Ajout manuel")
    await ctx.send(f"+{montant:,} € crédités sur {membre.display_name}")

@bot.command(name="remove")
@commands.check(lambda ctx: is_admin(ctx))
async def remove_money(ctx, membre: discord.Member, montant: int):
    if montant <= 0: return await ctx.send("Montant positif.")
    creer_compte(membre.id); ancien = get_solde(membre.id)
    if ancien < montant: return await ctx.send("Fonds insuffisants.")
    update_solde(membre.id, ancien - montant)
    await ctx.send(f"-{montant:,} € débités de {membre.display_name}")

@bot.command(name="set")
@commands.check(lambda ctx: is_admin(ctx))
async def set_money(ctx, membre: discord.Member, montant: int):
    if montant < 0: return await ctx.send("Montant ≥ 0.")
    creer_compte(membre.id); ancien = get_solde(membre.id)
    update_solde(membre.id, montant)
    await ctx.send(f"Solde de {membre.display_name} → {montant:,} €")

@bot.command(name="logs")
@commands.check(lambda ctx: is_admin(ctx))
async def logs(ctx, nombre: int = 20):
    conn = sqlite3.connect(DB_NAME); c = conn.cursor()
    c.execute("SELECT * FROM transactions ORDER BY id DESC LIMIT ?", (nombre,))
    rows = c.fetchall(); conn.close()
    if not rows: return await ctx.send("Aucune transaction.")
    embed = discord.Embed(title=f"Historique ({len(rows)} dernières)", color=0xffaa00)
    for row in rows:
        ts, typ, a, c, m = row[1], row[2], row[3], row[4], row[5]
        embed.add_field(name=ts, value=f"{typ} • {m:,} € • <@{a}> → <@{c}>", inline=False)
    await ctx.author.send(embed=embed)
    await ctx.send("Logs envoyés en MP !")

@bot.command(name="banque")
async def aide(ctx):
    embed = discord.Embed(title="Commandes Bank-Life-Bot", color=0x0099ff)
    embed.add_field(name="!solde", value="Voir ton solde", inline=False)
    embed.add_field(name="!virement @user montant", value="Envoyer de l'argent", inline=False)
    if is_admin(ctx):
        embed.add_field(name="Admin", value="!add | !remove | !set | !logs", inline=False)
    await ctx.author.send(embed=embed)
    await ctx.send(f"{ctx.author.mention} Commandes envoyées en MP !")
    await ctx.message.delete()

# ————— LANCEMENT —————
bot.run(os.getenv("DISCORD_TOKEN"))
