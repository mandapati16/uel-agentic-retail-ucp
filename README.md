# uel-agentic-retail-ucp
Xiatech Summer Programme — Agentic AI for Retail. UCP  agent track.

## 1. Clone and set up the environment
 
```bash
git clone https://github.com/mandapati16/uel-agentic-retail-ucp.git
cd uel-agentic-retail-ucp.git
 
# Create and activate a virtual environment
python -m venv mcp-env
source mcp-env/bin/activate      # on Windows: mcp-env\Scripts\activate
 
# Install dependencies
pip install -r requirements.txt
```
 
`requirements.txt`:
```
fastmcp>=0.2.0
google-cloud-bigquery>=3.25.0
google-cloud-secret-manager>=2.20.0
pydantic>=2.7.0
python-dotenv>=1.0.0
mcp
```
 
---
 
## 2. Configure your environment (`.env`)
 
Copy the example file and fill in your project details:
 
```bash
cp .env.example .env
```
 
`.env.example`:
```
GCP_PROJECT=xfuze-nextgen-poc
BQ_DATASET=xfuze_analytics
BQ_ACTIONS_DATASET=xfuze_analytics
SECRET_NAME=data-access-mcp-json-key
GCP_REGION=europe-west2
```
 
Notes:
- `SECRET_NAME` must match the Secret Manager secret containing the
  `data-access-mcp` service account's JSON key (`data-access-mcp-json-key`
  by default — confirm the exact name with your coordinator if it differs).
- `BQ_ACTIONS_DATASET` only needs to differ from `BQ_DATASET` if
  `agent_actions` is split into its own dataset — check with DevOps before
  changing this.
- **Do not commit your filled-in `.env`.** It's already listed in
  `.gitignore`. It doesn't contain secrets itself (the real credentials live
  in Secret Manager, fetched at runtime), but keep project-specific config
  out of version control regardless.
`server.py` loads this automatically via `python-dotenv`:
```python
from dotenv import load_dotenv
load_dotenv()
```
 
### Persisting env vars across shell sessions (Cloud Shell users)
 
Cloud Shell does **not** persist `export`ed variables between sessions. If
you'd rather not rely on `.env`/`load_dotenv()` everywhere (e.g. for ad-hoc
`bq` CLI commands too), add the same variables to `~/.bashrc` instead:
 
```bash
cat >> ~/.bashrc << 'EOF'
export GCP_PROJECT=xfuze-nextgen-poc
export BQ_DATASET=xfuze_analytics
export SECRET_NAME=data-access-mcp-json-key
export GCP_REGION=europe-west2
EOF
source ~/.bashrc
```
 
---
 
## 3. Run the server locally
 
```bash
python server.py
```
 
This starts the MCP server over **stdio** — it will sit silently, waiting for
a client to connect. That's expected behaviour, not a hang.
 
On successful startup you should see:
```
Server:      xfuze-data-access, <version>
INFO     Starting MCP server 'xfuze-data-access' with transport 'stdio'
```
 
If you instead see a `KeyError` for one of the env vars, your `.env` isn't
being loaded or wasn't filled in — see Troubleshooting below.
 
---
 
## 4. Test it
 
### scripted client (recommended for quick checks / CI)
 
```bash
python test_client.py
```
 
This connects over stdio, lists available tools, and calls a couple of tools
against real data to confirm the full chain (Secret Manager → BigQuery auth →
query → MCP response) works end to end. Edit the `product_id`/`order_id`
values in the script to match real IDs in your dataset — get one with:
 
```bash
bq query --use_legacy_sql=false \
  'SELECT product_id FROM `xfuze-nextgen-poc.xfuze_analytics.dim_products` LIMIT 5'
```
 
---
 
## 5. Validate the data contract
 
Checks the live BigQuery schema against the documented contract
(`data_contracts.md`) and fails loudly on drift — missing tables, renamed/
missing columns, type mismatches, or suspiciously empty tables.
 
```bash
python validate_contract.py
```
 
Run this after pulling latest, or any time something that used to work starts
throwing unexpected `KeyError`/validation errors — it's the fastest way to
tell "the schema changed underneath us" apart from "the code has a bug."

 
---
