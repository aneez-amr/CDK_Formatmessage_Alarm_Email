#!/usr/bin/env python3
from aws_cdk import App

from sns_alarm_stack import SnsAlarmStack


app = App()
monitoring_email = app.node.try_get_context("monitoringEmail")
alarmed_lambda_name = app.node.try_get_context("alarmedLambdaName")

SnsAlarmStack(
    app,
    "EventbridgeAlarmErrorStack",
    monitoring_email=monitoring_email,
    alarmed_lambda_name=alarmed_lambda_name,
)

app.synth()
