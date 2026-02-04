# Eventbridge Alarm Error (CDK Python)

This project is now implemented in Python 3.13 using AWS CDK v2. The stack
creates the SNS topic, CloudWatch alarm, and EventBridge rule that formats
alarm metadata into a multiline notification before publishing to your email.

## Setup

1. Create/activate a Python 3.13 virtual environment (e.g., `python3.13 -m venv .venv`).
2. Install CDK dependencies:
   ```sh
   pip install -r requirements.txt
   ```

## Useful commands

* `npx cdk synth`  emit the CloudFormation template
* `npx cdk diff`   compare the deployed stack with the current definition
* `npx cdk deploy` deploy the stack to your AWS account
"# CDK_Formatmessage_Alarm_Email" 
