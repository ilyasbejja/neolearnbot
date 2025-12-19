import discord
from discord.ext import commands
import aiohttp
from supabase import create_client, Client
import json
import requests
import os


def download_drive_pdf(url, filename):
    session = requests.Session()
    response = session.get(url, stream=True)

    # Cas fichiers volumineux (page de confirmation Google)
    for key, value in response.cookies.items():
        if key.startswith("download_warning"):
            params = {"confirm": value}
            response = session.get(url, params=params, stream=True)

    with open(filename, "wb") as f:
        for chunk in response.iter_content(32768):
            if chunk:
                f.write(chunk)

# ================== CONFIG ==================

SUPABASE_URL = "https://vxvrhsccwooqnloxxayy.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZ4dnJoc2Njd29vcW5sb3h4YXl5Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjU3NDIwMjAsImV4cCI6MjA4MTMxODAyMH0.AzbbdLcEvWWy-6wq0LIG_k3SPBvnl5ltzvzg7ITffuQ"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# ================== OLLAMA SESSION ==================



SYSTEM_PROMPT = (
    "Tu es un assistant universitaire. "
    "Tu réponds en français. "
    "Sois clair, concis et  tres tres tres précis."
)

# ================== FONCTION LLM STREAM ==================

import os
from groq import Groq
from dotenv import load_dotenv

client = Groq(api_key="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")

def ask_llm(prompt: str) -> str:
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "Tu es un assistant éducatif précis et concis."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=300
    )
    return response.choices[0].message.content.strip()


# ================== COMMANDE ASK ==================

@bot.command()
async def ask(ctx, *, question):
    try:
        # Appelle LLM et récupère la réponse complète
        response = ask_llm(question)  # retourne une str

        # Envoie la réponse sur Discord
        await ctx.send(response)

    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")
  

        

# ================== COMMANDE COURS (version simple Supabase) ==================



# ================== COMMANDE TEST ==================

@bot.command()
async def test(ctx):
    try:
        result = supabase.table("coursi").select("*").execute()
        await ctx.send("Connexion Supabase OK ✅")
        s = ""
        for row in result.data:
            p= row["matiere"] +  " " + row["url"]
            
            
            await ctx.send(p)
    except Exception as e:
        await ctx.send(f"Erreur dans test : {e}")
        

# ================== EVENTS ==================

@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")

        
@bot.command()
async def resume(ctx, limit=50):
    messages = []
    async for msg in ctx.channel.history(limit=limit):
        if not msg.author.bot:
            messages.append(f"{msg.author.name}: {msg.content}")

    messages.reverse()
    conversation = "\n".join(messages)

    summary = await summarize(conversation)

    await ctx.send(f"📝 **Résumé de la conversation :**\n{summary}")
    

@bot.command()
async def cours(ctx, *, question):
    try:
        # 🔹 Récupérer toutes les matières depuis Supabase
        result = supabase.table("coursi").select("matiere").execute()
        if not result.data:
            await ctx.send("❌ La base de données est vide.")
            return

        matieres = [row["matiere"] for row in result.data]
        matieres_str = ", ".join(matieres)
        
        
        # 🔹 Générer le prompt LLM dynamiquement
        prompt = (
            f"Tu vas prendre la requête et choisir la matière la plus proche parmi : {matieres_str}. "
            "Réponds uniquement par le nom exact de la matière, ne corrige pas ni ne modifie."
        )
        full_prompt = f"{question} {prompt}"

        # 🔹 Obtenir la réponse du LLM (str)
        matiere = ask_llm(full_prompt).strip().lower()

        # 🔹 Afficher la matière détectée
        await ctx.send(f"🧠 Matière détectée : **{matiere}**")

        # 🔹 Rechercher dans Supabase
        result = supabase.table("coursi").select("*").ilike("matiere", f"%{matiere}%").limit(1).execute()
        if not result.data:
            await ctx.send("❌ Aucun cours trouvé pour cette matière.")
            return

        cours = result.data[0]
        url = cours["url"]
        filename = cours["matiere"].replace(" ", "_") + ".pdf"

        # 🔹 Afficher spinner pendant téléchargement
        async with ctx.typing():
            download_drive_pdf(url, filename)

        # 🔹 Envoyer PDF
        await ctx.send(
            content=f"📘 **Cours : {cours['matiere']}**",
            file=discord.File(filename)
        )

        # 🔹 Nettoyer
        os.remove(filename)

    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")




# ================== RUN ==================

bot.run("MTQ0ODc4MTIzODkzMTQyMzUwMw.GK7vkS.nF9vZVl7r43VB7dDTYAXH_-9EDWZ48aj0cakGU")



