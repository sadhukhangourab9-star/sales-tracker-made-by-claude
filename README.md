# OrderTrack — Mobile Sales Order Tracker (Google Sheets Edition)

A Flask web application to track online platform orders for mobile resale businesses. 
**Now powered by Google Sheets for a 100% free, stateless deployment!**

## Deployment via Render (Free Tier)
1. Push this repo to GitHub.
2. Create a new account at [render.com](https://render.com).
3. Click **New → Web Service** → connect your GitHub repo.
4. Render will use `render.yaml` automatically.
5. In the Render Dashboard for this web service, go to **Environment**, and add a Secret File or Environment Variable:
   - Key: `GOOGLE_CREDENTIALS_JSON`
   - Value: *(Paste the entire contents of your Google Service Account JSON file here)*
6. Ensure you have created a Google Sheet named `OrderTrack_DB` and shared it with the service account email!

The app will auto-generate the necessary tabs (cards, platforms, models, etc.) on first boot!
