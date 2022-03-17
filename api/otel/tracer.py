# Class for using OTel tracing

from inspect import Attribute
from jinja2 import Undefined
from opentelemetry import trace

# OTLP & Jaeger exporters
from opentelemetry.exporter.jaeger.thrift import JaegerExporter                         
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter      
# API for Auto-Instrumentation
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

# SDK libraries 
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    ConsoleSpanExporter,
    SimpleSpanProcessor,
    BatchSpanProcessor,
)

class Tracer:
    tracer = Undefined

    def __init__(self, serviceName, currentFileName):
        self.serviceName = serviceName
        self.currentFileName = currentFileName
    
    def configTracer(self):

        # Use this if u want export directly to Jaeger 
        jaeger_exporter = JaegerExporter(       
            agent_host_name="jaeger",
            agent_port=6831,
        )

        # For export to OTeL Gateway or Agent
        OTLP_exporter = OTLPSpanExporter(  
            endpoint="otel-collector:4317",     
            insecure=True,
        )   

        trace.set_tracer_provider(
            TracerProvider(
                resource=Resource.create({SERVICE_NAME: f"{self.serviceName}"})
            )
        )
        trace.get_tracer_provider().add_span_processor(
            # SimpleSpanProcessor(ConsoleSpanExporter())
            # BatchSpanProcessor(jaeger_exporter),
            BatchSpanProcessor(OTLP_exporter)
        )

        # Assign Trace class to self.trace variable, for using the Trace package in another files
        self.trace = trace

    def autoInstrumentationFlask(self, serviceApp):
        FlaskInstrumentor().instrument_app(serviceApp)
    
    def autoInstrumentationRequest(self):
        RequestsInstrumentor().instrument() 
        