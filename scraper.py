name: SUUMO Scraper Auto Check

on:
  schedule:
    - cron: '0 * * * *'
  workflow_dispatch:

jobs:
  run-scraper:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements.txt

      - name: Run scraper
        env:
          SPREADSHEET_ID: ${{ secrets.SPREADSHEET_ID }}
          GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
        run: |
          python scraper.py
