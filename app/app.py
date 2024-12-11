import os
import yaml
from flask import Flask, render_template, jsonify, request
from datetime import datetime
import cohere
import json
from dotenv import load_dotenv
from flask_mail import Mail, Message
from weasyprint import HTML
import base64
import tempfile

load_dotenv(dotenv_path=".env", override=True)

co = cohere.ClientV2(
    api_key=os.getenv("COHERE_API_KEY")
)
PROMPT_DIR = os.path.join("app/prompts")
MODEL = "command-r-plus-08-2024"
RERANK = "rerank-v3.5"
TOP_N = 3

app = Flask(__name__, static_folder='static')

# email config
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('EMAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('EMAIL_PASSWORD')
mail = Mail(app)

def convert_recommendations_to_yaml():
    # Load the JSON data
    with open('app/data/recommendation-log.json', 'r') as file:
        data = json.load(file)
    
    yaml_documents = []
    
    for item in data:
        # Create a dictionary with failure summary and recommendation first
        formatted_item = {
            'failureSummary': item['failureSummary'],
            'recommendation': item['recommendation'],
            'id': item['id'],
            'timestamp': item['timestamp']
        }
        
        # Convert the dictionary to YAML string
        yaml_string = yaml.dump(
            formatted_item,
            default_flow_style=False,  # Use block style formatting
            sort_keys=False,  # Maintain the order of keys
            allow_unicode=True  # Support unicode characters
        )
        
        yaml_documents.append(yaml_string)
    
    return yaml_documents, data


YAML_DOCS, JSON_DOCS = convert_recommendations_to_yaml()


@app.route('/api/generate-summary', methods=['POST'])
def generate_summary():
    try:
        log_data = request.json.get('logData')  # Changed to expect logData in the request
        if not log_data:
            return jsonify({'error': 'No log data provided'}), 400

        # get log title and map it to prompt
        log_title = log_data.get('title', '').lower().replace(' ', '-')
        prompt_mapping = {
            'page-load': 'log-page-load-v1.txt',
            'bid-start': 'log-bid-start-v1.txt',
            'bid-complete': 'log-bid-complete-v1.txt',
            'render-start': 'log-render-start-v1.txt',
            'render-failure': 'log-render-failure-v1.txt'
        }

        prompt_file = prompt_mapping.get(log_title)
        if not prompt_file:
            # fall back to generic prompt
            prompt_file = 'log-page-load-v1.txt'
        
        # read the appropriate prompt file
        prompt_path = os.path.join(PROMPT_DIR, prompt_file)
        try:
            with open(prompt_path, 'r') as f:
                prompt = f.read()
        except FileNotFoundError:
            print(f"Prompt file not found: {prompt_path}")
            # Fallback to page load prompt if file is missing
            with open(os.path.join(PROMPT_DIR, 'log-page-load-v1.txt'), 'r') as f:
                prompt = f.read()

        messages = [
            {"role": "user", "content": prompt.format(log_data=json.dumps(log_data, indent=2))}
        ]
        response = co.chat(
            model=MODEL,
            messages=messages
        ).message.content[0].text

        return jsonify({
            'success': True,
            'summary': response
        })
    except Exception as e:
        print(f"Error generating summary: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to generate summary'
        }), 500


@app.route('/api/generate-recommendations', methods=['POST'])
def generate_recommendations():
    try:
        summaries = request.json.get('summaries')
        if not summaries:
            return jsonify({'error': 'No summaries provided'}), 400

        # Format the summaries for the prompt
        formatted_summaries = "\n\n".join([
            f"{log_type}:\n{summary}"
            for log_type, summary in summaries.items()
        ])
        failure_summary = summaries.get("Render Failure", "")
        assert failure_summary != ""

        # retrieve top 3 documents
        rank_res = co.rerank(
            model=RERANK,
            query=failure_summary,
            documents=YAML_DOCS,
            top_n=TOP_N,
            return_documents=True
        ).results

        docs = "\n\n".join([doc.document.text for doc in rank_res[:1]])
        doc_idx = [doc.index for doc in rank_res]
        linked_fc = [JSON_DOCS[idx]['id'] for idx in doc_idx]
        
        # Load and format the recommendation prompt
        with open(os.path.join(PROMPT_DIR, 'alert-recommendation-v1.txt'), 'r') as f:
            prompt = f.read()

        messages = [
            {
                "role": "user", 
                "content": prompt.format(docs=docs, formatted_summaries=formatted_summaries)
            }
        ]

        response = co.chat(
            model=MODEL,
            messages=messages
        ).message.content[0].text

        print(response)

        return jsonify({
            'success': True,
            'recommendations': response,
            "links": linked_fc,
        })
    
    except Exception as e:
        print(f"Error generating recommendations: {str(e)}")
        return jsonify({
            'success': False,
            'error': 'Failed to generate recommendations'
        }), 500


@app.route('/api/send-alert', methods=['POST'])
def send_alert():
    try:
        data = request.json
        html_content = data.get('html')
        if not html_content:
            return jsonify({"error": "No HTML content provided."}), 400

        # create temp file for pdf
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            # generate pdf from html
            HTML(string=html_content).write_pdf(tmp.name)
            print(os.getenv("ALERT_EMAIL"))
            # create and send email with PDF attachment
            msg = Message(
                subject="ALERT: Ad Render Failure Report",
                sender=app.config['MAIL_USERNAME'],
                recipients=[os.getenv("ALERT_EMAIL")]
            )

            msg.body = """
    Please find attached the Ad Render Failure Report. This report contains detailed information about a failure event.
            """

            with open(tmp.name, 'rb') as pdf_file:
                msg.attach(
                    'ad_failure_report.pdf',
                    'application/pdf',
                    pdf_file.read()
                )

            mail.send(msg)

        os.unlink(tmp.name)
        return jsonify({
            'success': True,
            'message': 'Email sent successfully'
        })
    
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return jsonify({
            "success": False,
            "error": "Failed to send email"
        }), 500

@app.template_filter('tojson')
def tojson_filter(s):
    return json.dumps(s)


# Sample data that was previously in React state
FAILURE_CHAINS = [
    {   
        "id": "FC-2342-123",
        "timestamp": "2024-12-06T14:23:15.233Z",
        "failureType": "Render Failure",
        "adUnit": "Sidebar-300x250",
        "pageUrl": "/article/123",
        "revenue_impact": "$2.45"
    },
    {
        "id": "FC-3542-323",
        "timestamp": "2024-12-06T15:45:22.156Z",
        "failureType": "Bid Timeout",
        "adUnit": "Header-728x90",
        "pageUrl": "/article/456",
        "revenue_impact": "$3.12"
    },
    {
        "id": "FC-4234-554",
        "timestamp": "2024-12-06T16:12:08.789Z",
        "failureType": "Creative Load Error",
        "adUnit": "InContent-300x250",
        "pageUrl": "/article/789",
        "revenue_impact": "$1.89"
    }
]

def get_full_log_data(chain_id):
    # Full log data implementation
    logs = [
        {
            "id": "LOG-98765a",
            "title": "Page Load",
            "status": "success",
            "timestamp": "2024-12-06T14:23:15.233Z",
            "data": {
                "timestamp": "2024-12-06T14:23:15.233Z",
                "sessionId": "s123456789",
                "publisherId": "pub-789",
                "pageUrl": "https://example-publisher.com/article/123",
                "userContext": {
                    "deviceType": "desktop",
                    "browser": "chrome",
                    "browserVersion": "120.0.0",
                    "viewport": [1920, 1080],
                    "connection": "4g"
                }
            },
            "summary": "Initial page load detected on desktop Chrome browser with 4G connection"
        },
        {
            "id": "LOG-98765b",
            "title": "Bid Start",
            "status": "success",
            "timestamp": "2024-12-06T14:23:15.250Z",
            "data": {
                "timestamp": "2024-12-06T14:23:15.250Z",
                "sessionId": "s123456789",
                "publisherId": "pub-789",
                "adUnitData": {
                    "adUnitId": "div-gpt-ad-1234567890",
                    "size": [300, 250],
                    "position": "sidebar"
                },
                "bidDetails": {
                    "indexExchangeBidId": "ix_bid_98765"
                }
            },
            "summary": "Bid request initiated for 300x250 sidebar ad placement"
        },
        {
            "id": "LOG-98765c",
            "title": "Bid Complete",
            "status": "success",
            "timestamp": "2024-12-06T14:23:15.383Z",
            "data": {
                "timestamp": "2024-12-06T14:23:15.383Z",
                "sessionId": "s123456789",
                "publisherId": "pub-789",
                "adUnitData": {
                    "adUnitId": "div-gpt-ad-1234567890",
                    "bidDetails": {
                         "indexExchangeBidId": "ix_bid_98765",
                         "bidPrice": 2.45,
                         "bidLatency": 150,
                         "bidStatus": "won",
                         "winningBidTime": "2024-12-06T14:23:15.383Z"
                    }
                }
            },
            "summary": "Successful bid won at $2.45 with 150ms latency"
        },
        {
             "id": "LOG-98765d",
             "title": "Render Start",
             "status": "success",
             "timestamp": "2024-12-06T14:23:15.400Z",
             "data": {
                  "timestamp": "2024-12-06T14:23:15.400Z",
                  "sessionId": "s123456789",
                  "publisherId": "pub-789",
                  "adUnitData": {
                       "adUnitId": "div-gpt-ad-1234567890",
                       "adCreativeId": "creative_456",
                       "renderStartTime": "2024-12-06T14:23:15.400Z"
                  }
            },
            "summary": "Ad creative rendering process initiated"
        },
        {
            "id": "LOG-98765e",
            "title": "Render Failure",
            "status": "failed",
            "timestamp": "2024-12-06T14:23:15.583Z",
            "data": {
                "timestamp": "2024-12-06T14:23:15.583Z",
                "sessionId": "s123456789",
                "publisherId": "pub-789",
                "adUnitData": {
                    "adUnitId": "div-gpt-ad-1234567890",
                    "adCreativeId": "creative_456"
                },
                "adRenderMetrics": {
                    "timeToFirstByte": None,
                    "renderStartTime": "2024-12-06T14:23:15.400Z",
                    "renderCompleteTime": None,
                    "viewability": 0,
                    "errorCode": "AD_RENDER_FAILURE",
                    "errorMessage": "Failed to load ad creative",
                    "failureTimestamp": "2024-12-06T14:23:15.583Z"
                },
                "performanceMetrics": {
                    "pageLoadTime": 3500,
                    "domInteractive": 2800,
                    "adFrameLoadTime": None,
                    "networkErrors": {
                        "type": "REQUEST_FAILED",
                        "details": "Network request to ad creative failed with status 503"
                    }
                }
            },
            "summary": "Ad rendering failed due to network error (503) when attempting to load creative content"
        }
    ]

    return logs

@app.route('/')
def index():
    return render_template('index.html', 
                         failure_chains=FAILURE_CHAINS,
                         publisher_name="TechNews Daily",
                         publisher_id="pub-789")

@app.route('/api/chain/<chain_id>')
def get_chain_details(chain_id):
    chain = next((c for c in FAILURE_CHAINS if c['id'] == chain_id), None)
    if not chain:
        return jsonify({"error": "Chain not found"}), 404

    logs = get_full_log_data(chain_id)
    
    # Pass additional error information
    error_info = {
        'error_code': 'AD_RENDER_FAILURE',  # You might want to extract this from logs
        'error_type': chain['failureType'],
        'page_load_time': '3500ms'  # You might want to extract this from logs
    }

    return render_template('chain_details.html',
                         chain_id=chain_id,
                         logs=logs,
                         publisher_name="TechNews Daily",
                         publisher_id="pub-7893as5qsd525asfd3525",
                         ad_unit=chain['adUnit'],
                         revenue_impact=chain['revenue_impact'],
                         **error_info)  # Unpack error info into template variables

if __name__ == '__main__':
    app.run(debug=True)