# Deploy Dashboard to Streamlit Cloud

## Quick Setup (Get Your Production URL in 5 minutes)

### 1. Push Your Code to GitHub
```powershell
# If not already a git repo:
git init
git add .
git commit -m "Initial commit"

# Create a new repo on GitHub, then:
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git branch -M main
git push -u origin main
```

### 2. Deploy to Streamlit Cloud

1. Go to **[share.streamlit.io](https://share.streamlit.io)**
2. Sign in with GitHub
3. Click **"New app"**
4. Select:
   - **Repository**: Your GitHub repo
   - **Branch**: main
   - **Main file path**: `serve_dashboard.py`
5. Click **"Deploy!"**

### 3. Configure Environment Variables

In Streamlit Cloud dashboard, add these secrets (Settings → Secrets):

```toml
# Database
DATABASE_URL = "your_database_url"

# API Keys (if needed)
OPENAI_API_KEY = "your_key_here"
GOOGLE_API_KEY = "your_key_here"

# Any other environment variables from your .env file
```

### 4. Your Production URL

After deployment, you'll get a URL like:
```
https://YOUR_USERNAME-YOUR_REPO_NAME-xxxxx.streamlit.app
```

This is your production URL to use for CORS configuration!

---

## Alternative: Deploy to Google Cloud Run (What You Have Configured)

You already have `cloudbuild.dashboard.yaml`. To deploy there:

```powershell
# Set your GCP project
gcloud config set project YOUR_PROJECT_ID

# Build and deploy
gcloud builds submit --config cloudbuild.dashboard.yaml
gcloud run deploy dashboard \
  --image gcr.io/YOUR_PROJECT_ID/dashboard \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

You'll get a URL like: `https://dashboard-xxxxx-uc.a.run.app`

---

## Comparison

| Platform | Cost | Setup Time | Best For |
|----------|------|------------|----------|
| **Streamlit Cloud** | Free | 5 min | Quick deployment, demos |
| **Google Cloud Run** | Pay-as-you-go | 15 min | Production, custom domains |

Choose Streamlit Cloud for fastest deployment!
