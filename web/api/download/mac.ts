export const config = { runtime: "edge" };

const REPO = "hughminhphan/schemagic";
const FALLBACK = `https://github.com/${REPO}/releases/latest`;

export default async function handler() {
  try {
    const response = await fetch(
      `https://api.github.com/repos/${REPO}/releases/latest`,
      { headers: { Accept: "application/vnd.github.v3+json" } }
    );

    if (!response.ok) {
      return Response.redirect(FALLBACK, 302);
    }

    const release = await response.json();
    const dmg = release.assets?.find(
      (a: { name: string }) => a.name.endsWith("_aarch64.dmg")
    );

    if (dmg) {
      return Response.redirect(dmg.browser_download_url, 302);
    }
    return Response.redirect(FALLBACK, 302);
  } catch {
    return Response.redirect(FALLBACK, 302);
  }
}
