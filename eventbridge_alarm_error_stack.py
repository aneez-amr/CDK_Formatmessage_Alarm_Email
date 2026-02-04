from aws_cdk import (
    Duration,
    Stack,
    aws_cloudwatch as cloudwatch,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
)
from constructs import Construct


class EventbridgeAlarmErrorStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        notification_topic = sns.Topic(
            self,
            "AlarmNotificationTopic",
            display_name="Alarm notification topic"
        )

        notification_topic.add_subscription(
            subscriptions.EmailSubscription("aneez@amrinnovations.com")
        )

        lambda_error_metric = cloudwatch.Metric(
            namespace="AWS/Lambda",
            metric_name="Errors",
            dimensions_map={"FunctionName": "ExampleLambdaFunction"},
            statistic="sum",
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

        alarm_fields: dict[str, str] = {
            "Alarm Name": "$.detail.alarmName",
            "State": "$.detail.state.value",
            "Reason": "$.detail.state.reason",
            "Time": "$.time",
            "Region": "$.region",
            "Account": "$.account",
        }

        formatted_message = "\n".join(
            f"{'' if index == 0 else '  '}{label}: {events.EventField.from_path(path)}"
            for index, (label, path) in enumerate(alarm_fields.items())
        )

        events.Rule(
            self,
            "AlarmStateChangeRule",
            event_pattern=events.EventPattern(
                source=["aws.cloudwatch"],
                detail_type=["CloudWatch Alarm State Change"],
                detail={"alarmName": [error_alarm.alarm_name]},
            ),
            targets=[
                events_targets.SnsTopic(
                    notification_topic,
                    message=events.RuleTargetInput.from_text(formatted_message),
                )
            ],
        )
