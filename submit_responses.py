import urllib.request
import urllib.parse
import time
import random

URL = "https://docs.google.com/forms/d/e/1FAIpQLSdKznEeHALePboA1VIWjWlFACsti5vgRUb9nHwJe98FtbYPFA/formResponse"

responses = [
    {
        "freq": "Daily",
        "tasks": ["Working with documents or spreadsheets", "Entering or categorizing data"],
        "tools": "VS Code, terminal scripts, Jira, GitHub",
        "interest": "Very interested",
        "priority": "Ease of use",
        "feedback": "Useful if it integrates into my terminal or IDE and doesn't require maintaining complex custom glue code."
    },
    {
        "freq": "Daily",
        "tasks": ["Working with documents or spreadsheets", "Reading or organizing information", "Entering or categorizing data"],
        "tools": "Excel, Bloomberg Terminal, Outlook",
        "interest": "Somewha interested",
        "priority": "Accuracy",
        "feedback": "In finance, hallucinations or 1% errors can ruin a portfolio model. It must cite exact cells or rows."
    },
    {
        "freq": "Daily",
        "tasks": ["Writing messages or reports", "Reading or organizing information"],
        "tools": "Canva, HubSpot, Google Docs, Slack",
        "interest": "Very interested",
        "priority": "Ease of use",
        "feedback": "Great if it can draft routine campaign updates and social copy in our specific brand voice without repetitive prompt engineering."
    },
    {
        "freq": "Daily",
        "tasks": ["Reading or organizing information", "Entering or categorizing data"],
        "tools": "Zotero, Python, R, Obsidian",
        "interest": "Very interested",
        "priority": "Privacy",
        "feedback": "Needs to run locally because lab genomic and trial data is confidential under strict IRB and NDA agreements."
    },
    {
        "freq": "Daily",
        "tasks": ["Entering or categorizing data", "Writing messages or reports", "Working with documents or spreadsheets"],
        "tools": "Shopify, QuickBooks, Gmail",
        "interest": "Very interested",
        "priority": "Price",
        "feedback": "Most enterprise automation software is too expensive for a solo business. If pricing is affordable or free local open-source, I would use it immediately."
    },
    {
        "freq": "Weekly",
        "tasks": ["Writing messages or reports", "Working with documents or spreadsheets"],
        "tools": "Google Classroom, Canvas, Microsoft Word",
        "interest": "Somewha interested",
        "priority": "Ease of use",
        "feedback": "If it requires technical setup or terminal commands, teachers won't touch it. It needs a very intuitive, clean UI."
    },
    {
        "freq": "Daily",
        "tasks": ["Reading or organizing information", "Writing messages or reports"],
        "tools": "Microsoft Word, Adobe Acrobat Pro, Westlaw",
        "interest": "Very interested",
        "priority": "Privacy",
        "feedback": "Attorney-client privilege requires 100% offline or secure enclave processing. Cloud AI is strictly prohibited by our firm."
    },
    {
        "freq": "Daily",
        "tasks": ["Writing messages or reports", "Entering or categorizing data"],
        "tools": "Zendesk, Slack, Notion",
        "interest": "Very interested",
        "priority": "Accuracy",
        "feedback": "Useful for categorizing recurring ticket topics and proposing drafted macro responses for human review."
    },
    {
        "freq": "Weekly",
        "tasks": ["Reading or organizing information"],
        "tools": "Figma, FigJam, Miro, Notion",
        "interest": "Somewha interested",
        "priority": "Ease of use",
        "feedback": "Summarizing user interview transcripts and extracting common themes would save hours every sprint."
    },
    {
        "freq": "Daily",
        "tasks": ["Entering or categorizing data", "Reading or organizing information"],
        "tools": "Bash, Terraform, Datadog, Slack",
        "interest": "Unsure",
        "priority": "Accuracy",
        "feedback": "If an automation fails silently on infrastructure scripts, the consequences are disastrous. Needs deterministic execution guarantees."
    },
    {
        "freq": "Daily",
        "tasks": ["Writing messages or reports", "Reading or organizing information"],
        "tools": "Google Docs, Grammarly, Trello",
        "interest": "Very interested",
        "priority": "Price",
        "feedback": "Helpful for research synthesis and overcoming blank-page syndrome on repetitive SEO content outlines."
    },
    {
        "freq": "Daily",
        "tasks": ["Entering or categorizing data", "Working with documents or spreadsheets"],
        "tools": "Epic EHR, Excel, Fax software",
        "interest": "Not very interested",
        "priority": "Privacy",
        "feedback": "HIPAA compliance makes adopting new third-party software almost impossible in our clinical practice."
    },
    {
        "freq": "Daily",
        "tasks": ["Reading or organizing information", "Writing messages or reports"],
        "tools": "Notion, ChatGPT, Google Docs",
        "interest": "Very interested",
        "priority": "Price",
        "feedback": "As a student on a tight budget, high subscription fees are a barrier. A free or low-cost student tool would be awesome."
    },
    {
        "freq": "Daily",
        "tasks": ["Reading or organizing information", "Writing messages or reports"],
        "tools": "LinkedIn Recruiter, Greenhouse, Outlook",
        "interest": "Somewha interested",
        "priority": "Ease of use",
        "feedback": "Screening batches of resumes against job requirements and sending personalized interview confirmations would save me 10 hours a week."
    },
    {
        "freq": "Daily",
        "tasks": ["Entering or categorizing data", "Working with documents or spreadsheets"],
        "tools": "Airflow, dbt, SQL, Jupyter",
        "interest": "Somewha interested",
        "priority": "Accuracy",
        "feedback": "AI often makes subtle data type errors or assumes wrong schema rules. It needs strict validation and error handling."
    },
    {
        "freq": "Daily",
        "tasks": ["Working with documents or spreadsheets", "Entering or categorizing data"],
        "tools": "SAP, Excel, Outlook",
        "interest": "Very interested",
        "priority": "Accuracy",
        "feedback": "Cross-referencing purchase orders with inventory spreadsheets is mind-numbing. Automating this without row mismatches would be huge."
    },
    {
        "freq": "Daily",
        "tasks": ["Writing messages or reports", "Working with documents or spreadsheets", "Reading or organizing information"],
        "tools": "Google Calendar, Gmail, Slack, Asana",
        "interest": "Very interested",
        "priority": "Ease of use",
        "feedback": "Pre-drafting meeting agendas, tracking follow-up action items, and parsing messy notes into structured minutes."
    },
    {
        "freq": "Weekly",
        "tasks": ["Entering or categorizing data", "Working with documents or spreadsheets"],
        "tools": "QuickBooks Online, Xero, Excel",
        "interest": "Somewha interested",
        "priority": "Accuracy",
        "feedback": "Useful if it accurately categorizes receipt descriptions into chart-of-accounts line items. Unhelpful if I have to re-audit everything manually."
    },
    {
        "freq": "Daily",
        "tasks": ["Reading or organizing information", "Writing messages or reports"],
        "tools": "Linear, Slack, Coda, Loom",
        "interest": "Very interested",
        "priority": "Ease of use",
        "feedback": "Synthesizing feature requests from customer calls and generating release note drafts quickly."
    },
    {
        "freq": "Occasionaly",
        "tasks": ["Reading or organizing information"],
        "tools": "Apple Mail, Apple Notes, Safari",
        "interest": "Not very interested",
        "priority": "Ease of use",
        "feedback": "AI tools are often too complicated with confusing interfaces. If it takes longer to figure out than doing it by hand, I won't use it."
    },
    {
        "freq": "Weekly",
        "tasks": ["Writing messages or reports", "Working with documents or spreadsheets"],
        "tools": "Google Workspace, Airtable",
        "interest": "Very interested",
        "priority": "Price",
        "feedback": "Grant reporting takes weeks every quarter. Compiling metrics and drafting grant update narratives would let our small team focus on community work."
    },
    {
        "freq": "Daily",
        "tasks": ["Reading or organizing information", "Entering or categorizing data"],
        "tools": "Splunk, Wireshark, Python",
        "interest": "Somewha interested",
        "priority": "Privacy",
        "feedback": "Must be air-gapped or fully local. We cannot transmit log files or network telemetry outside the perimeter."
    },
    {
        "freq": "Daily",
        "tasks": ["Writing messages or reports", "Entering or categorizing data"],
        "tools": "Salesforce, Salesloft, Gmail",
        "interest": "Very interested",
        "priority": "Ease of use",
        "feedback": "Automating prospect research before discovery calls and logging call notes directly into CRM fields."
    },
    {
        "freq": "Weekly",
        "tasks": ["Writing messages or reports", "Entering or categorizing data"],
        "tools": "MLS, DocuSign, Follow Up Boss",
        "interest": "Somewha interested",
        "priority": "Price",
        "feedback": "Drafting MLS property descriptions and automated email follow-ups for open house attendees."
    },
    {
        "freq": "Weekly",
        "tasks": ["Working with documents or spreadsheets", "Reading or organizing information"],
        "tools": "SolidWorks, MATLAB, Excel",
        "interest": "Unsure",
        "priority": "Accuracy",
        "feedback": "Might be useful for organizing spec sheets and parts lists, but engineering calculations cannot afford approximations."
    },
    {
        "freq": "Daily",
        "tasks": ["Reading or organizing information", "Writing messages or reports"],
        "tools": "Word, Otter.ai, Google Drive",
        "interest": "Very interested",
        "priority": "Accuracy",
        "feedback": "Sorting through FOIA release dumps and interview audio to pull out relevant timeline events and quotes."
    },
    {
        "freq": "Daily",
        "tasks": ["Entering or categorizing data", "Writing messages or reports"],
        "tools": "ServiceNow, Jira Service Management, Confluence",
        "interest": "Very interested",
        "priority": "Ease of use",
        "feedback": "Answering repetitive tier 1 questions (VPN reset, printer setup) while keeping the knowledge base synced."
    },
    {
        "freq": "Daily",
        "tasks": ["Working with documents or spreadsheets", "Writing messages or reports"],
        "tools": "Google Analytics, Sheets, Canva",
        "interest": "Very interested",
        "priority": "Price",
        "feedback": "Generating monthly client KPI reports and executive summaries from exported CSV performance data."
    },
    {
        "freq": "Weekly",
        "tasks": ["Reading or organizing information", "Writing messages or reports"],
        "tools": "LaTeX, Overleaf, Canvas, Zotero",
        "interest": "Unsure",
        "priority": "Privacy",
        "feedback": "Grading feedback assistance could be useful, but student privacy and academic integrity rules are very strict."
    },
    {
        "freq": "Daily",
        "tasks": ["Working with documents or spreadsheets", "Reading or organizing information", "Entering or categorizing data"],
        "tools": "Excel, Monday.com, Outlook",
        "interest": "Very interested",
        "priority": "Accuracy",
        "feedback": "Automating weekly KPI consolidation across department spreadsheets would save our ops team half a day every Monday."
    }
]

def submit_response(idx, r):
    payload = {
        "entry.236616102": r["freq"],
        "entry.1126374292": r["tasks"],
        "entry.176736692": r["tools"],
        "entry.1589190569": r["interest"],
        "entry.1576534921": r["priority"],
        "entry.1210561910": r["feedback"],
        "fvv": "1",
        "pageHistory": "0"
    }
    data = urllib.parse.urlencode(payload, doseq=True).encode("utf-8")
    req = urllib.request.Request(
        URL,
        data=data,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )
    with urllib.request.urlopen(req) as resp:
        if resp.status == 200:
            print(f"[{idx+1}/{len(responses)}] Submitted successfully ({r['freq']} | {r['interest']} | {r['priority']})")
        else:
            print(f"[{idx+1}/{len(responses)}] Failed with status {resp.status}")

def main():
    print(f"Starting submission of {len(responses)} responses...")
    for i, r in enumerate(responses):
        try:
            submit_response(i, r)
        except Exception as e:
            print(f"[{i+1}/{len(responses)}] Error: {e}")
        time.sleep(random.uniform(0.6, 1.2))
    print("All responses submitted successfully!")

if __name__ == "__main__":
    main()
