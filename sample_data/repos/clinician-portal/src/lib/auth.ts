import { jwtVerify, createRemoteJWKSet } from "jose";

// JWKS from identity-svc (cached 5 min by jose). See T-006/JWKS staleness.
const JWKS = createRemoteJWKSet(
  new URL("https://auth.medscribe.internal/.well-known/jwks.json"),
);

export interface Principal {
  sub: string;
  role: string;
  tenantId: string;
}

export async function verify(req: {
  headers: Record<string, string | undefined>;
}): Promise<Principal> {
  const auth = req.headers["authorization"] ?? "";
  const token = auth.replace(/^Bearer /, "");
  const { payload } = await jwtVerify(token, JWKS, {
    issuer: "https://auth.medscribe.internal",
    audience: "medscribe-api",
  });

  // FIXME(T-011): tenant_id is taken from a request header instead of the
  // verified JWT claim. A caller can set x-tenant-id to any value and access
  // another tenant's data. Must use payload.tenant_id (server-side claim).
  const tenantId = (req.headers["x-tenant-id"] as string) || (payload.tenant_id as string);

  return { sub: payload.sub as string, role: payload.role as string, tenantId };
}
