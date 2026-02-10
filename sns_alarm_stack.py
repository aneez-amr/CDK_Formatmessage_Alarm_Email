import os

from aws_cdk import CfnOutput, Duration, Stack
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from constructs import Construct


APPLICATION_NAME = os.getenv("APPLICATION_NAME", "EventbridgeAlarmError")
ENVIRONMENT_TAG = os.getenv("ENVIRONMENT_TAG", "DEV")
ALARMED_LAMBDA_NAME_DEFAULT = "ExampleApiLambda"


class SnsAlarmStack(Stack):
    """Simple stack that publishes CloudWatch alarms to SNS + formatter Lambda."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        self.monitoring_email = kwargs.pop("monitoring_email", None)
        self.alarmed_lambda_name = kwargs.pop("alarmed_lambda_name", None)
        super().__init__(scope, construct_id, **kwargs)
        self.monitoring_email = self.monitoring_email or os.getenv("MONITORING_EMAIL")
        self.alarmed_lambda = (
            self.alarmed_lambda_name
            or os.getenv("ALARMED_LAMBDA_NAME", ALARMED_LAMBDA_NAME_DEFAULT)
        )

        self.raw_topic = sns.Topic(
            self,
            "RawAlarmNotifications",
            display_name="CloudWatch alarm topic",
        )

        self.formatted_topic = sns.Topic(
            self,
            "FormattedAlarmNotifications",
            display_name="Formatted alarm notifications",
        )

        if self.monitoring_email:
            self.formatted_topic.add_subscription(
                subs.EmailSubscription(self.monitoring_email)
            )

        formatter = lambda_.Function(
            self,
            "AlarmFormatterFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="alarm_formatter.lambda_handler",
            code=lambda_.Code.from_asset(os.path.join(os.path.dirname(__file__), "lambda")),
            timeout=Duration.seconds(30),
            memory_size=256,
            environment={
                "FORMATTED_TOPIC_ARN": self.formatted_topic.topic_arn,
                "APPLICATION_NAME": APPLICATION_NAME,
                "ENVIRONMENT": ENVIRONMENT_TAG,
            },
        )

        self.formatted_topic.grant_publish(formatter)
        self.raw_topic.add_subscription(subs.LambdaSubscription(formatter))
        errors_metric = cw.Metric(
            namespace="AWS/Lambda",
            metric_name="Errors",
            dimensions_map={"FunctionName": self.alarmed_lambda},
            statistic="Sum",
            period=Duration.minutes(1),
        )

        error_alarm = cw.Alarm(
            self,
            "LambdaErrorAlarm",
            metric=errors_metric,
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            alarm_description=f"Error alarm for {self.alarmed_lambda}",
        )

        error_alarm.add_alarm_action(cw_actions.SnsAction(self.raw_topic))

        CfnOutput(
            self,
            "RawAlarmTopicArn",
            value=self.raw_topic.topic_arn,
            description="SNS topic used for incoming alarm events",
        )

        CfnOutput(
            self,
            "FormattedNotificationTopicArn",
            value=self.formatted_topic.topic_arn,
            description="SNS topic that receives formatted messages",
        )

        CfnOutput(
            self,
            "FormatterLambdaArn",
            value=formatter.function_arn,
            description="Formatter Lambda ARN",
        )
