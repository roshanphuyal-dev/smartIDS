from traffic_engine.session_builder.session_builder import SessionBuilder
from feature_engine.extractors.session_feature_extractor import SessionFeatureExtractor
from feature_engine.feature_store.feature_store import FeatureStore


class PacketProcessor:
    def __init__(self):
        self.session_builder = SessionBuilder()
        self.feature_extractor = SessionFeatureExtractor()
        self.feature_store = FeatureStore()

    def process(self, packet):
        session = self.session_builder.process_packet(packet)

        features = self.feature_extractor.extract(session)

        self.feature_store.add(features)

        print(features)
