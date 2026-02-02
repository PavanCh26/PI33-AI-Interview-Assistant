import requests
import os
import json

class FirebaseRest:
    def __init__(self):
        self.project_id = os.getenv("FIREBASE_PROJECT_ID", "pi33-firebase")
        # Fallback to the known public key if not in env
        self.api_key = os.getenv("FIREBASE_API_KEY", "AIzaSyB8KuRNyNmffaEII-TCSiqUbFufGofxGrk") 
        self.base_url = f"https://firestore.googleapis.com/v1/projects/{self.project_id}/databases/(default)/documents"

    def verify_id_token(self, id_token):
        """Verifies a Firebase ID token using the Identity Toolkit API."""
        try:
            # Using the Identity Toolkit which is more reliable for Firebase ID tokens
            url = f"https://identitytoolkit.googleapis.com/v1/accounts:lookup?key={self.api_key}"
            payload = {"idToken": id_token}
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'users' in data and len(data['users']) > 0:
                    user_info = data['users'][0]
                    # Map to the same format as decoded_token for backward compatibility
                    return {
                        'email': user_info.get('email'),
                        'sub': user_info.get('localId'),
                        'name': user_info.get('displayName', 'User'),
                        'picture': user_info.get('photoUrl', '')
                    }
            
            # Fallback to tokeninfo if Identity Toolkit fails
            url = f"https://oauth2.googleapis.com/tokeninfo?id_token={id_token}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()
                
            print(f"DEBUG: All verification methods failed. Status: {response.status_code}, Response: {response.text}")
        except Exception as e:
            print(f"DEBUG: Verification exception: {e}")
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
            if v is None: continue
            if isinstance(v, str): fields[k] = {'stringValue': v}
            elif isinstance(v, bool): fields[k] = {'booleanValue': v}
            elif isinstance(v, (int, float)): fields[k] = {'integerValue': str(int(v))}
            elif isinstance(v, dict): fields[k] = {'mapValue': {'fields': self._to_firestore_dict(v)}}
            elif isinstance(v, list): 
                vals = []
                for x in v:
                    if isinstance(x, str): vals.append({'stringValue': x})
                    elif isinstance(x, dict): vals.append({'mapValue': {'fields': self._to_firestore_dict(x)}})
                fields[k] = {'arrayValue': {'values': vals}}
        return fields

    def get_document(self, collection_path, document_id):
        """Fetches a document from Firestore using the REST API."""
        try:
            # Document ID might contain dots/signs, but Firestore handles them in URL path usually.
            # However, ensure we lowercase email-based IDs for consistency.
            doc_id = str(document_id).lower()
            url = f"{self.base_url}/{collection_path}/{doc_id}?key={self.api_key}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                return {k: self._convert_value(v) for k, v in data.get('fields', {}).items()}
            elif response.status_code == 404:
                return None # Normal for non-existent users
            else:
                print(f"DEBUG: Firestore Get failed. Path: {collection_path}/{doc_id}, Status: {response.status_code}, Response: {response.text}")
            return None
        except Exception as e:
            print(f"Firestore Get Error: {e}")
            return None

    def set_document(self, collection_path, document_id, data):
        """Creates or overwrites a document in Firestore."""
        try:
            doc_id = str(document_id).lower()
            url = f"{self.base_url}/{collection_path}/{doc_id}?key={self.api_key}"
            payload = {'fields': self._to_firestore_dict(data)}
            response = requests.patch(url, json=payload, timeout=10)
            if response.status_code in [200, 201]:
                return True
            print(f"DEBUG: Firestore Set failed. Path: {collection_path}/{doc_id}, Status: {response.status_code}, Response: {response.text}")
            return False
        except Exception as e:
            print(f"Firestore Set Error: {e}")
            return False

    def update_document(self, collection_path, document_id, data):
        """Updates specific fields in a Firestore document."""
        try:
            doc_id = str(document_id).lower()
            url = f"{self.base_url}/{collection_path}/{doc_id}?key={self.api_key}"
            params = []
            for k in data.keys():
                params.append(f"updateMask.fieldPaths={k}")
            
            url += "&" + "&".join(params) # Use & since key is already there
            payload = {'fields': self._to_firestore_dict(data)}
            response = requests.patch(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Firestore Update Error: {e}")
            return False

    def get_collection(self, collection_path, limit=10):
        """Fetches multiple documents from a collection."""
        try:
            url = f"{self.base_url}/{collection_path}?pageSize={limit}&key={self.api_key}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                docs = response.json().get('documents', [])
                results = []
                for doc in docs:
                    name_parts = doc['name'].split('/')
                    doc_id = name_parts[-1]
                    res = {k: self._convert_value(v) for k, v in doc.get('fields', {}).items()}
                    res['id'] = doc_id
                    results.append(res)
                return results
            return []
        except Exception as e:
            print(f"Firestore Collection Error: {e}")
            return []
