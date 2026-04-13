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
    const asset = release.assets?.find((a: { name: string }) =>
      /\.(msi|exe)$/i.test(a.name)
    );

    if (asset) {
      return Response.redirect(asset.browser_download_url, 302);
    }
    return Response.redirect(FALLBACK, 302);
  } catch {
    return Response.redirect(FALLBACK, 302);
  }
}
