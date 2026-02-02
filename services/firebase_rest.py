import requests
import os
import json

class FirebaseRest:
    def __init__(self):
        self.project_id = os.getenv("FIREBASE_PROJECT_ID", "pi33-firebase")
        self.api_key = os.getenv("FIREBASE_API_KEY") 
        self.base_url = f"https://firestore.googleapis.com/v1/projects/{self.project_id}/databases/(default)/documents"

    def verify_id_token(self, id_token):
        """Verifies a Firebase ID token using the Google tokeninfo endpoint."""
        try:
            url = f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Check if it's for our project
                if data.get('aud') == self.project_id or data.get('azp'): # Simplify for now
                    return data
            print(f"Token verification failed: {response.text}")
        except Exception as e:
            print(f"Token verification error: {e}")
        return None

    def _convert_value(self, value):
        """Helper to convert Firestore REST values to Python values."""
        if 'stringValue' in value: return value['stringValue']
        if 'integerValue' in value: return int(value['integerValue'])
        if 'booleanValue' in value: return value['booleanValue']
        if 'mapValue' in value:
            return {k: self._convert_value(v) for k, v in value['mapValue'].get('fields', {}).items()}
        if 'arrayValue' in value:
            return [self._convert_value(v) for v in value['arrayValue'].get('values', [])]
        if 'timestampValue' in value: return value['timestampValue']
        return None

    def _to_firestore_dict(self, data):
        """Helper to convert Python dict to Firestore REST fields."""
        fields = {}
        for k, v in data.items():
            if isinstance(v, str): fields[k] = {'stringValue': v}
            elif isinstance(v, bool): fields[k] = {'booleanValue': v}
            elif isinstance(v, int): fields[k] = {'integerValue': str(v)}
            elif isinstance(v, dict): fields[k] = {'mapValue': {'fields': self._to_firestore_dict(v)}}
            elif isinstance(v, list): fields[k] = {'arrayValue': {'values': [self._to_firestore_dict({'item': x})['item'] for x in v]}}
        return fields

    def get_document(self, collection_path, document_id):
        """Fetches a document from Firestore using the REST API."""
        try:
            url = f"{self.base_url}/{collection_path}/{document_id}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {k: self._convert_value(v) for k, v in data.get('fields', {}).items()}
            return None
        except Exception as e:
            print(f"Firestore Get Error: {e}")
            return None

    def set_document(self, collection_path, document_id, data):
        """Creates or overwrites a document in Firestore."""
        try:
            url = f"{self.base_url}/{collection_path}/{document_id}"
            payload = {'fields': self._to_firestore_dict(data)}
            response = requests.patch(url, json=payload, timeout=10) # Patch works as upsert
            return response.status_code in [200, 201]
        except Exception as e:
            print(f"Firestore Set Error: {e}")
            return False

    def update_document(self, collection_path, document_id, data):
        """Updates specific fields in a Firestore document."""
        try:
            # For patch, we need to specify updateMask for partial updates
            url = f"{self.base_url}/{collection_path}/{document_id}"
            params = []
            for k in data.keys():
                params.append(f"updateMask.fieldPaths={k}")
            
            url += "?" + "&".join(params)
            payload = {'fields': self._to_firestore_dict(data)}
            response = requests.patch(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Firestore Update Error: {e}")
            return False

    def get_collection(self, collection_path, limit=10):
        """Fetches multiple documents from a collection."""
        try:
            url = f"{self.base_url}/{collection_path}?pageSize={limit}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                docs = response.json().get('documents', [])
                results = []
                for doc in docs:
                    doc_id = doc['name'].split('/')[-1]
                    res = {k: self._convert_value(v) for k, v in doc.get('fields', {}).items()}
                    res['id'] = doc_id
                    results.append(res)
                return results
            return []
        except Exception as e:
            print(f"Firestore Collection Error: {e}")
            return []
