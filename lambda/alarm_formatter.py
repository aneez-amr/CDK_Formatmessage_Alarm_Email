import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List

import boto3

logger = logging.getLogger("alarm_formatter")
logger.setLevel(logging.INFO)

sns_client = boto3.client("sns")

FORMATTED_TOPIC_ARN = os.environ.get("FORMATTED_TOPIC_ARN", "")
APPLICATION_NAME = os.environ.get("APPLICATION_NAME", "EventbridgeAlarmError")
ENVIRONMENT = os.environ.get("ENVIRONMENT", "DEV")
INCLUDE_RAW_PAYLOAD = os.environ.get("INCLUDE_RAW_PAYLOAD", "false").lower() == "true"


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Process SNS-triggered CloudWatch alarm events and publish formatted alerts."""
    logger.info("Received event %s", event)

    records = event.get("Records", [])
    if not records:
        logger.warning("No SNS records found in the event")
        return {"statusCode": 400, "body": "No SNS records provided"}

    message_ids: List[str] = []
    for index, record in enumerate(records, start=1):
        sns = record.get("Sns", {})
        raw_message = sns.get("Message")
        if not raw_message:
            logger.warning("Record %s missing SNS message body; skipping", index)
            continue

        payload = normalize_message(raw_message)
        subject = format_subject(payload)
        body = format_body(payload)

        if not FORMATTED_TOPIC_ARN:
            logger.error("FORMATTED_TOPIC_ARN not set; cannot publish formatted alert")
            continue

        response = sns_client.publish(
            TopicArn=FORMATTED_TOPIC_ARN,
            Subject=subject[:100],
            Message=body,
        )
        message_id = response.get("MessageId")
        if message_id:
            message_ids.append(message_id)
            logger.info("Published formatted alarm message %s", message_id)

    return {"statusCode": 200, "messageIds": message_ids}


def normalize_message(message: str) -> Dict[str, Any]:
    """Parse the SNS alarm payload if it is JSON; otherwise wrap it."""
    try:
        payload = json.loads(message)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        logger.debug("Alarm payload is not JSON; leaving raw text")
    return {"raw_message": message}


def format_subject(payload: Dict[str, Any]) -> str:
    """Generate a concise subject line for the formatted alert."""
    state = payload.get("NewStateValue") or payload.get("StateValue") or "UNKNOWN"
    alarm_name = payload.get("AlarmName") or payload.get("Alarm") or "CloudWatch Alarm"
    severity_label = severity_text(state)
    return f"{severity_label} - {alarm_name}"


def format_body(payload: Dict[str, Any]) -> str:
    severity = severity_text(payload.get("NewStateValue") or payload.get("StateValue") or "UNKNOWN")
    alarm_name = payload.get("AlarmName", "Unknown")
    from_state = payload.get("OldStateValue", "UNKNOWN")
    to_state = payload.get("NewStateValue") or payload.get("StateValue") or "UNKNOWN"
    reason = payload.get("NewStateReason") or payload.get("StateReason", "No reason provided")
    timestamp_text = format_timestamp(payload.get("StateChangeTime") or payload.get("StateTransitionTime"))
    trigger_info = extract_trigger_info(payload.get("Trigger") or {})
    lines = [
        f"{severity} - {alarm_name}",
        "======================================================================",
        "",
        "🔔 STATE CHANGE",
        f"From: {from_state} → To: {to_state}",
        "",
        "📊 REASON",
        reason,
        "",
        "📈 METRIC DETAILS",
        f"• Metric: {trigger_info['metric_name']}",
        f"• Namespace: {trigger_info['namespace']}",
        f"• Statistic: {trigger_info['statistic']}",
        f"• Period: {trigger_info['period']} minute",
        f"• Evaluation Periods: {trigger_info['evaluation_periods']}",
        f"• Threshold: {trigger_info['threshold']}",
        f"• Dimensions: {trigger_info['dimensions']}",
        "",
        "📌 SOURCE RESOURCE",
        payload.get("AlarmArn", "Unknown"),
        "",
        "🧾 LOG ENTRY",
        "----------------------------------------------------------------------",
        "not available",
        "----------------------------------------------------------------------",
        "",
        "ℹ️ ADDITIONAL INFO",
        f"• Time: {timestamp_text}",
        f"• Region: {payload.get('Region', 'Unknown')}",
        f"• Account: {payload.get('AWSAccountId', 'Unknown')}",
    ]
    if INCLUDE_RAW_PAYLOAD:
        lines.extend(
            [
                "",
                "Raw Payload:",
                json.dumps(payload, indent=2, default=str),
            ]
        )

    return "\n".join(lines)


def severity_text(state: str) -> str:
    mapping = {
        "ALARM": "CRITICAL",
        "INSUFFICIENT_DATA": "WARNING",
        "OK": "RESOLVED",
    }
    return mapping.get(state.upper(), "INFO")


def format_timestamp(value: str) -> str:
    if not value:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return f"{dt.strftime('%Y-%m-%d %H:%M:%S')} UTC"
    except ValueError:
        return value


def extract_trigger_info(trigger: Dict[str, Any]) -> Dict[str, str]:
    if not trigger:
        return {
            "metric_name": "Unknown",
            "namespace": "Unknown",
            "statistic": "Unknown",
            "period": "Unknown",
            "evaluation_periods": "Unknown",
            "threshold": "Unknown",
            "dimensions": "None",
        }

    metric_name = trigger.get("MetricName") or trigger.get("Metric") or "Unknown"
    namespace = trigger.get("Namespace", "Unknown")
    statistic = trigger.get("Statistic") or trigger.get("Stat", "Unknown")
    period = trigger.get("Period") or trigger.get("PeriodInSeconds") or "Unknown"
    evaluation_periods = trigger.get("EvaluationPeriods", "Unknown")
    threshold = trigger.get("Threshold", "Unknown")
    dimensions = trigger.get("Dimensions") or trigger.get("dimension") or []
    if isinstance(dimensions, list):
        dimension_text = ", ".join(
            f"{d.get('name')}={d.get('value')}" for d in dimensions if isinstance(d, dict)
        )
        dimensions = dimension_text or "None"
    else:
        dimensions = str(dimensions)

    return {
        "metric_name": metric_name,
        "namespace": namespace,
        "statistic": statistic,
        "period": period,
        "evaluation_periods": evaluation_periods,
        "threshold": threshold,
        "dimensions": dimensions,
    }
