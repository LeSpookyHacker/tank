import { MongoClient } from "mongodb";

// Connection URI is provided at runtime from GCP Secret Manager via the
// MONGO_URI env injected by the Cloud Run service account (Workload Identity).
const uri = process.env.MONGO_URI ?? "mongodb+srv://localhost/medscribe";
let client: MongoClient | null = null;

async function getClient(): Promise<MongoClient> {
  if (!client) {
    client = new MongoClient(uri);
    await client.connect();
  }
  return client;
}

export async function getNotesCollection() {
  const c = await getClient();
  return c.db("medscribe").collection("notes");
}
