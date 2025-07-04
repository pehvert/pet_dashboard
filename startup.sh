#!/bin/bash
pip install -r requirements.txt
streamlit run app.py --server.port 8000 --server.enableCORS false
