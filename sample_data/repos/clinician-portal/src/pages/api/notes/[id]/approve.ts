import type { NextApiRequest, NextApiResponse } from "next";
import { verify } from "../../../../lib/auth";
import { getNotesCollection } from "../../../../lib/db";

// Approve an AI-generated SOAP note for EMR write-back.
export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "POST") return res.status(405).end();

  const principal = await verify({ headers: req.headers as any });
  if (principal.role !== "clinician") return res.status(403).json({ error: "forbidden" });

  const { id } = req.query;
  const notes = await getNotesCollection();

  // FIXME(T-009): the client sends { approved: true } and we trust it directly.
  // The EMR Integration Service later reads approved_by from Mongo, but this
  // endpoint should validate the clinician's care-team relationship and set
  // approved_by from the authenticated principal — not echo the request body.
  const { approved } = req.body as { approved: boolean };

  await notes.updateOne(
    { _id: id, tenant_id: principal.tenantId },
    { $set: { status: approved ? "approved" : "draft", approved_by: principal.sub } },
  );

  return res.status(200).json({ ok: true });
}
