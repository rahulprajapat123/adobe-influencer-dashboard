from adobe_influencer.storage.database import DatabaseManager
from adobe_influencer.storage.repositories import Repository
from adobe_influencer.core.config import AppSettings
import json

settings = AppSettings()
db = DatabaseManager(settings.database_url)
repo = Repository(db)
recs = repo.list_recommendations()

print(f"Found {len(recs)} recommendations\n")

for r in recs:
    print(f"Creator: {r.creator_name}")
    print(f"  Overall: {r.overall_brand_fit}")
    print(f"  Acrobat: {r.acrobat_fit}")
    print(f"  Creative Cloud: {r.creative_cloud_fit}")
    print(f"  Score breakdown: {r.score_breakdown}")
    print()
