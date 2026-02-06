from aws_cdk import (
    Duration,
    Stack,
    aws_cloudwatch as cloudwatch,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
)
from constructs import Construct

class EventbridgeAlarmErrorStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # 1. SNS Topic for Notifications
        notification_topic = sns.Topic(
            self,
            "AlarmNotificationTopic",
            display_name="Alarm notification topic"
        )
        notification_topic.add_subscription(
            subscriptions.EmailSubscription("aneez.rafeek@gmail.com")
        )

         # 5. The Example Lambda (The one that fails)
        example_lambda = _lambda.Function(
            self,
            "ExampleLambdaFunction",
            function_name="ExampleLambdaFunction", # Fixed name for the metric
            runtime=_lambda.Runtime.PYTHON_3_10,
            handler="index.handler",
            code=_lambda.Code.from_inline(
                """
import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    # This creates the log entry for the client
    logger.error("FATAL_ERROR: Database connection failed in production!")
    
    # This automatically increments the 'Errors' metric for the alarm
    raise Exception("Triggering the Alarm for testing")
"""
            )
        )

        # 2. Metric & Alarm
        # We use the standard AWS/Lambda Errors metric
        lambda_error_metric = cloudwatch.Metric(
            namespace="AWS/Lambda",
            metric_name="Errors",
            dimensions_map={"FunctionName": "ExampleLambdaFunction"},
            statistic="Sum",
            period=Duration.minutes(1)
        )

        error_alarm = cloudwatch.Alarm(
            self,
            "LambdaErrorAlarm",
            alarm_name="ExampleLambdaErrorAlarm",
            metric=lambda_error_metric,
            evaluation_periods=1,
            threshold=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING
        )

        # 3. The Formatter Lambda (The "Enricher")
        formatter_function = _lambda.Function(
            self,
            "AlarmFormatter",
            runtime=_lambda.Runtime.PYTHON_3_10,
            handler="index.handler",
            code=_lambda.Code.from_inline(
                """
import json
import os
import time
from datetime import datetime, timedelta
import boto3

sns = boto3.client("sns")
logs_client = boto3.client("logs")

def handler(event, context):
    detail = event.get("detail", {})
    state = detail.get("state", {})
    config = detail.get("configuration", {})
    
    # Extract Function Name from the alarm dimensions
    source_resource = "ExampleLambdaFunction" # Fallback
    try:
        metrics = config.get("metrics", [])
        if metrics:
            source_resource = metrics[0]['metricStat']['metric']['dimensions']['FunctionName']
    except:
        pass

    # FETCH LOGS: Look back 5 minutes to find the "verursachenden Logeintrag"
    causing_log = "No specific log entry found."
    if source_resource:
        try:
            log_group = f"/aws/lambda/{source_resource}"
            # Use time.time() for reliable millisecond timestamps
            end_time = int(time.time() * 1000)
            start_time = int((time.time() - 300) * 1000)
            
            response = logs_client.filter_log_events(
                logGroupName=log_group,
                filterPattern="?ERROR ?Exception ?Fail",
                startTime=start_time,
                endTime=end_time,
                limit=1
            )
            if response.get("events"):
                causing_log = response["events"][0]["message"]
        except Exception as e:
            causing_log = f"Failed to retrieve log: {str(e)}"

    # Format Message
    payload = [
        f"CRITICAL - {detail.get('alarmName')}",
        "========================================",
        f"STATE: {state.get('value')}",
        f"REASON: {state.get('reason')}",
        "",
        "🧾 VERURSACHENDER LOGEINTRAG",
        "----------------------------------------",
        causing_log.strip(),
        "----------------------------------------",
        "",
        f"RESOURCE: {source_resource}",
        f"TIME: {event.get('time')}"
    ]

    sns.publish(
        TopicArn=os.environ["ALARM_TOPIC_ARN"],
        Subject=f"ALARM: {detail.get('alarmName')}",
        Message="\\n".join(payload)
    )
"""
            ),
            environment={"ALARM_TOPIC_ARN": notification_topic.topic_arn},
            timeout=Duration.minutes(1),
        )

        # Permissions for Formatter
        formatter_function.add_to_role_policy(iam.PolicyStatement(
            actions=["logs:FilterLogEvents", "logs:DescribeLogStreams"],
            resources=["*"]
        ))
        notification_topic.grant_publish(formatter_function)

        # 4. EventBridge Rule
        events.Rule(
            self,
            "AlarmStateChangeRule",
            event_pattern=events.EventPattern(
                source=["aws.cloudwatch"],
                detail_type=["CloudWatch Alarm State Change"],
                detail={"alarmName": [error_alarm.alarm_name]},
            ),
            targets=[events_targets.LambdaFunction(formatter_function)],
        )

       