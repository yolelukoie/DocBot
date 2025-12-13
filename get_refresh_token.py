from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/drive.file"]

def main():
    flow = InstalledAppFlow.from_client_secrets_file(
        "Secret/client_secret_971248889962-2nhdb6v4smgc9l3rhf93skrthplb4c24.apps.googleusercontent.com.json",  # имя твоего файла
        SCOPES,
    )
    creds = flow.run_local_server(port=0)
    print("ACCESS TOKEN:", creds.token)
    print("REFRESH TOKEN:", creds.refresh_token)
    print("CLIENT ID:", creds.client_id)
    print("CLIENT SECRET:", creds.client_secret)

if __name__ == "__main__":
    main()