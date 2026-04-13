import { signIdentityToken, verifyRequestToken } from "@/lib/auth";

export const dynamic = "force-dynamic";

interface Props {
  searchParams: Promise<{ token?: string }>;
}

export default async function VerifyPage({ searchParams }: Props) {
  const { token } = await searchParams;
  const payload = token ? verifyRequestToken(token) : null;

  if (!payload) {
    return (
      <Shell title="Link expired">
        <p>This sign-in link is invalid or has expired.</p>
        <p>Return to scheMAGIC and request a new one.</p>
      </Shell>
    );
  }

  const identityToken = signIdentityToken(payload.email);
  const deepLink = `schemagic://auth?token=${encodeURIComponent(identityToken)}`;
  const deepLinkJson = JSON.stringify(deepLink);

  return (
    <Shell title="Opening scheMAGIC...">
      <p>We&apos;re handing you back to the app. You can close this tab.</p>
      <p>
        If nothing happens,{" "}
        <a href={deepLink} style={{ color: "#FF2D78", fontWeight: 600 }}>
          click here
        </a>{" "}
        to return to scheMAGIC.
      </p>
      <meta httpEquiv="refresh" content={`0;url=${deepLink}`} />
      <script
        dangerouslySetInnerHTML={{
          __html: `window.location.replace(${deepLinkJson});`,
        }}
      />
    </Shell>
  );
}

function Shell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: "-apple-system, system-ui, sans-serif",
        background: "#0A0A0A",
        color: "#fff",
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "48px 24px",
      }}
    >
      <div
        style={{
          maxWidth: 480,
          width: "100%",
          background: "#111",
          border: "1px solid #1A1A1A",
          borderRadius: 8,
          padding: 32,
        }}
      >
        <h1 style={{ fontSize: 24, margin: "0 0 16px" }}>{title}</h1>
        <div style={{ color: "#888", lineHeight: 1.5, display: "flex", flexDirection: "column", gap: 12 }}>
          {children}
        </div>
      </div>
    </div>
  );
}
