# Class for using OTel tracing

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter      

# SDK libraries 
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider

class Tracer:
    def __init__(self, serviceName, currentFileName):
        self.serviceName = serviceName
        self.currentFileName = currentFileName
    
    def configTracer(self):
        OTLPSpan_exporter = OTLPSpanExporter(  
            endpoint=os.getenv("OTLP_EXPORTER_ENDPOINT", "otel-collector:4317"),     
            insecure=True,
        )   

        trace.set_tracer_provider(
            TracerProvider(
                resource=Resource.create({SERVICE_NAME: f"{self.serviceName}"})
            )
        )

        self.OTLPSpanExporter = OTLPSpan_exporter

