import discord
from discord.ext import commands
import sqlite3
import datetime
import os
import asyncio

# ————— CONFIGURATION —————
PREFIX = "!"
ADMIN_ROLE_NAME = "Banquier"
LOG_CHANNEL_ID = None  # Mets l'ID du salon logs si tu veux

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)

# ————— BASE DE DONNÉES —————
DB_NAME = "banque.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS comptes (
                 user_id INTEGER PRIMARY KEY,
                 solde INTEGER DEFAULT 20000
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
                 id INTEGER PRIMARY KEY AUTOINCREMENT,
                 timestamp TEXT,
                 type TEXT,
                 auteur_id INTEGER,
                 cible_id INTEGER,
                 montant INTEGER,
                 solde_avant INTEGER,
                 solde_apres INTEGER,
                 commentaire TEXT
                 )''')
    conn.commit()
    conn.close()

def get_solde(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT solde FROM comptes WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def creer_compte(user_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO comptes (user_id, solde) VALUES (?, 20000)", (user_id,))
    conn.commit()
    conn.close()

def update_solde(user_id, nouveau_solde):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO comptes (user_id, solde) VALUES (?, ?)", (user_id, nouveau_solde))
    conn.commit()
    conn.close()

def log_transaction(type_transac, auteur_id, cible_id, montant, solde_avant, solde_apres, commentaire=""):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""INSERT INTO transactions
                 (timestamp, type, auteur_id, cible_id, montant, solde_avant, solde_apres, commentaire)
                 VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
              (now, type_transac, auteur_id, cible_id, montant, solde_avant, solde_apres, commentaire))
    conn.commit()
    conn.close()

# ————— ÉVÉNEMENTS —————
@bot.event
async def on_ready():
    init_db()
    print(f"✅ {bot.user} est en ligne – Banque RP prête !")
    print(f"   Joueurs dans la base : {len([r for r in sqlite3.connect(DB_NAME).cursor().execute('SELECT * FROM comptes')])}")

# ————— FONCTIONS UTILITAIRES —————
def is_admin(ctx):
    return any(role.name == ADMIN_ROLE_NAME for role in ctx.author.roles)

async def send_log_embed(channel_or_user, embed):
    try:
        await channel_or_user.send(embed=embed)
    except:
        pass

# ————— COMMANDES JOUEURS —————
@bot.command(name="solde")
async def solde(ctx):
    creer_compte(ctx.author.id)
    solde_actuel = get_solde(ctx.author.id)
    embed = discord.Embed(title="🏦 Votre compte Life-Bank", color=0x00ff00)
    embed.add_field(name="Titulaire", value=ctx.author.display_name, inline=False)
    embed.add_field(name="Solde", value=f"**{solde_actuel:,} €**".replace(",", " "), inline=False)
    embed.set_footer(text="NextLifeRP – Banque officielle")
    await ctx.send(embed=embed, delete_after=15)
    await ctx.message.delete()

@bot.command(name="virement")
async def virement(ctx, membre: discord.Member, montant: int):
    if montant <= 0:
        return await ctx.send("❌ Le montant doit être positif.")
    if membre.bot:
        return await ctx.send("❌ Tu ne peux pas virer de l'argent à un bot.")
    if membre == ctx.author:
        return await ctx.send("❌ Tu ne peux pas te virer de l'argent à toi-même.")

    creer_compte(ctx.author.id)
    creer_compte(membre.id)

    solde_exp = get_solde(ctx.author.id)
    if solde_exp < montant:
        return await ctx.send(f"❌ Fonds insuffisants. Tu as seulement {solde_exp:,} €.")

    # Débit expéditeur
    update_solde(ctx.author.id, solde_exp - montant)
    log_transaction("Virement envoyé", ctx.author.id, membre.id, montant, solde_exp, solde_exp - montant, f"Vers {membre}")

    # Crédit destinataire
    solde_dest = get_solde(membre.id)
    update_solde(membre.id, solde_dest + montant)
    log_transaction("Virement reçu", ctx.author.id, membre.id, montant, solde_dest, solde_dest + montant, f"De {ctx.author}")

    embed = discord.Embed(title="✅ Virement effectué", color=0x00ff00)
    embed.add_field(name="Expéditeur", value=ctx.author.mention, inline=True)
    embed.add_field(name="Destinataire", value=membre.mention, inline=True)
    embed.add_field(name="Montant", value=f"**{montant:,} €**".replace(",", " "), inline=True)
    embed.add_field(name="Nouveau solde", value=f"**{solde_exp - montant:,} €**".replace(",", " "), inline=False)
    await ctx.send(embed=embed)

# ————— COMMANDES ADMIN —————
@bot.command(name="add")
@commands.check(lambda ctx: is_admin(ctx))
async def add_money(ctx, membre: discord.Member, montant: int):
    if montant <= 0: return await ctx.send("Montant positif svp.")
    creer_compte(membre.id)
    ancien = get_solde(membre.id)
    update_solde(membre.id, ancien + montant)
    log_transaction("Admin +", ctx.author.id, membre.id, montant, ancien, ancien + montant, "Ajout manuel")
    await ctx.send(f"✅ +{montant:,} € crédités sur le compte de {membre.display_name}")

@bot.command(name="remove")
@commands.check(lambda ctx: is_admin(ctx))
async def remove_money(ctx, membre: discord.Member, montant: int):
    if montant <= 0: return await ctx.send("Montant positif svp.")
    creer_compte(membre.id)
    ancien = get_solde(membre.id)
    if ancien < montant:
        return await ctx.send(f"❌ Le joueur n'a que {ancien:,} €")
    update_solde(membre.id, ancien - montant)
    log_transaction("Admin -", ctx.author.id, membre.id, montant, ancien, ancien - montant, "Retrait manuel")
    await ctx.send(f"✅ -{montant:,} € débités du compte de {membre.display_name}")

@bot.command(name="set")
@commands.check(lambda ctx: is_admin(ctx))
async def set_money(ctx, membre: discord.Member, montant: int):
    if montant < 0: return await ctx.send("Montant positif ou zéro.")
    creer_compte(membre.id)
    ancien = get_solde(membre.id)
    update_solde(membre.id, montant)
    log_transaction("Admin SET", ctx.author.id, membre.id, montant - ancien, ancien, montant, f"Set à {montant} €")
    await ctx.send(f"✅ Solde de {membre.display_name} défini à {montant:,} €")

@bot.command(name="logs")
@commands.check(lambda ctx: is_admin(ctx))
async def logs(ctx, nombre: int = 20):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""SELECT timestamp, type, auteur_id, cible_id, montant, solde_avant, solde_apres, commentaire
                 FROM transactions ORDER BY id DESC LIMIT ?""", (nombre,))
    rows = c.fetchall()
    conn.close()

    if not rows:
        return await ctx.send("Aucune transaction enregistrée.")

    embed = discord.Embed(title=f"📑 Historique des {len(rows)} dernières transactions", color=0xffaa00)
    
    for row in rows:
        ts, typ, auth_id, cible_id, mont, avant, apres, com = row
        auteur = bot.get_user(auth_id) or f"<@{auth_id}>"
        cible = bot.get_user(cible_id) or f"<@{cible_id}>"
        texte = f"{typ} • {mont:,} € • {auteur} → {cible}"
        if com: texte += f" ({com})"
        embed.add_field(name=ts, value=texte, inline=False)

    destination = ctx.author
    if LOG_CHANNEL_ID:
        destination = bot.get_channel(LOG_CHANNEL_ID) or ctx.author

    await send_log_embed(destination, embed)
    if destination != ctx.author:
        await ctx.send("📑 Logs envoyés dans le salon configuré.")
    else:
        await ctx.send("📑 Logs envoyés en MP.")

# ————— MESSAGE D'AIDE —————
@bot.command(name="banque")
async def aide_banque(ctx):
    embed = discord.Embed(title="🏦 Life-Bank – Commandes", color=0x0099ff)
    embed.add_field(name="!solde", value="Voir ton solde", inline=False)
    embed.add_field(name="!virement @user montant", value="Envoyer de l'argent", inline=False)
    if is_admin(ctx):
        embed.add_field(name="Commandes Banquier", value="`!add`, `!remove`, `!set`, `!logs`", inline=False)
    await ctx.author.send(embed=embed)
    await ctx.send(f"{ctx.author.mention} Je t'ai envoyé la liste des commandes en MP !")
    await ctx.message.delete()

# ————— LANCEMENT —————
bot.run(os.getenv("DISCORD_TOKEN"))  # Token dans Environment Variables sur Render
