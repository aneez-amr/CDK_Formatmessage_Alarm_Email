#!/usr/bin/env python3
from aws_cdk import App

from eventbridge_alarm_error_stack import EventbridgeAlarmErrorStack


app = App()
EventbridgeAlarmErrorStack(app, "EventbridgeAlarmErrorStack")
app.synth()
