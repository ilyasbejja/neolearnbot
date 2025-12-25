import discord
from discord.ext import commands
from supabase import create_client, Client
import json
import requests
import os
from groq import Groq
from dotenv import load_dotenv
import re
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm

load_dotenv()

# ================== FONCTION UTILISEES ==================
def create_pdf_resume(text, filename="resume.pdf", title="Résumé du document"):
    styles = getSampleStyleSheet()
    story = []

    # Titre
    title_style = styles["Title"]
    story.append(Paragraph(title, title_style))

    # Texte du résumé
    body_style = styles["BodyText"]
    for line in text.split("\n"):
        story.append(Paragraph(line, body_style))

    pdf = SimpleDocTemplate(
        filename,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )

    pdf.build(story)

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

def download_discord_file(url, filename):
    r = requests.get(url)
    with open(filename, "wb") as f:
        f.write(r.content)

def extract_pdf_text(filename):
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(filename) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        return text
    except Exception as e:
        print("Erreur extraction PDF :", e)
        return ""

def summarize_document(document_text):
    user_prompt = f"""
Tu es un assistant pédagogique.
Résume le document suivant de manière claire et structurée.

Consignes :
- Utilise des titres
- Explique simplement
- Rends les formules mathématiques lisibles en ASCII
- Mets les formules dans des blocs de code

Document :
\"\"\"
{document_text}
\"\"\"
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
        max_tokens=1500
    )

    return response.choices[0].message.content.strip()

# ================== CONFIG SUPABASE ==================

SUPABASE_URL = "https://vxvrhsccwooqnloxxayy.supabase.co"
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================== CONFIG BOT DISCORD ==================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

with open(("./prompt.txt"), "r", encoding="utf-8") as f:
    SYSTEM_PROMPT=f.read()
    
# ================== CONFIG LLM ==================

client = Groq(api_key="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")

def ask_llm(prompt: str) -> str:
    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0.2,
        max_tokens=2000
    )
    return response.choices[0].message.content.strip()

# ================== COMMANDE RESUME ==================
@bot.command()
async def resume(ctx):
    if not ctx.message.attachments:
        await ctx.send("❌ Veuillez d'abord uploader un fichier PDF.")
        return

    attachment = ctx.message.attachments[0]

    if not attachment.filename.lower().endswith(".pdf"):
        await ctx.send("❌ Seuls les fichiers PDF sont acceptés.")
        return

    filename = attachment.filename

    status = await ctx.send("⬇️ Téléchargement du fichier...")
    download_discord_file(attachment.url, filename)

    await status.edit(content="📄 Extraction du texte du PDF...")
    text = extract_pdf_text(filename)

    if not text.strip():
        await status.edit(content="❌ Impossible d'extraire du texte depuis ce PDF.")
        os.remove(filename)
        return

    await status.edit(content="🧠 Génération du résumé...")
    summary = summarize_document(text)
    pdf_filename = "resume.pdf"

    create_pdf_resume(
        summary,
        filename=pdf_filename,
        title=f"Résumé — {attachment.filename}"
    )

    await ctx.send(
        content="📄 **Résumé généré en PDF :**",
        file=discord.File(pdf_filename)
    )

    os.remove(pdf_filename)

def extract_json(text):
    try:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        else:
            return None
    except Exception as e:
        print("Erreur parsing JSON:", e)
        return None
      
def generate_qcm_from_text(text, n=5):
    prompt = f"""
À partir du texte suivant, génère {n} questions QCM.

Règles STRICTES :
- Réponds UNIQUEMENT en JSON
- 1 seule bonne réponse par question
- Choix A, B, C, D
- Niveau universitaire

Format EXACT :
{{
  "questions": [
    {{
      "question": "...",
      "choices": {{
        "A": "...",
        "B": "...",
        "C": "...",
        "D": "..."
      }},
      "answer": "A"
    }}
  ]
}}

TEXTE :
{text[:4000]}
"""
    response = ask_llm(prompt)

    qcm_data = extract_json(response)
    if not qcm_data:
        raise ValueError("Impossible de parser le JSON du QCM. LLM a renvoyé :\n" + response)

    return qcm_data
# ================== COMMANDE QCM ==================

@bot.command()
async def qcm(ctx, n: int = 5):
    if not ctx.message.attachments:
        await ctx.send("❌ Veuillez uploader un fichier PDF.")
        return

    attachment = ctx.message.attachments[0]
    filename = attachment.filename
    await attachment.save(filename)

    await ctx.send("📥 Fichier reçu. Analyse en cours...")

    text = extract_pdf_text(filename)
    qcm_data = generate_qcm_from_text(text, n)

    questions = qcm_data["questions"]

    message = "**📝 QCM – Répondez avec ex: `1B 2C 3A`**\n\n"
    for i, q in enumerate(questions, 1):
        message += f"**{i}. {q['question']}**\n"
        for k, v in q["choices"].items():
            message += f"{k}) {v}\n"
        message += "\n"

    await ctx.send(message)

    # Sauvegarde temporaire
    bot.qcm_cache = {
        "answers": [q["answer"] for q in questions]
    }

    os.remove(filename)

@bot.command()
async def repondre(ctx, *, responses):
    if not hasattr(bot, "qcm_cache"):
        await ctx.send("❌ Aucun QCM en cours.")
        return

    correct = bot.qcm_cache["answers"]
    user_answers = responses.upper().split()

    score = 0
    result = ""

    for i, ua in enumerate(user_answers):
        good = correct[i]
        ok = ua[-1] == good
        score += ok
        result += f"Q{i+1} : {'✅' if ok else '❌'} (Bonne réponse : {good})\n"

    await ctx.send(
        f"📊 **Résultat : {score}/{len(correct)}**\n\n{result}"
    )

    del bot.qcm_cache

@bot.command()
async def ask(ctx, *, question):
    try:
        # Appelle LLM et récupère la réponse complète
        response = ask_llm(question)  # retourne une str

        # Envoie la réponse sur Discord
        await ctx.send(response)

    except Exception as e:
        await ctx.send(f"❌ Erreur : {e}")
  
# ================== COMMANDE COURS ==================

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
        matiere = ask_llm(full_prompt).strip().lower()
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
        

# ================== COMMAND  ==================

@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")
    
# ================== RUN ==================

bot.run(os.getenv("DISCORD_TOKEN"))

