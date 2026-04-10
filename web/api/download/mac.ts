import type { VercelRequest, VercelResponse } from "@vercel/node";

const REPO = "hughminhphan/schemagic";

export default async function handler(req: VercelRequest, res: VercelResponse) {
  try {
    const response = await fetch(
      `https://api.github.com/repos/${REPO}/releases/latest`,
      { headers: { Accept: "application/vnd.github.v3+json" } }
    );

    if (!response.ok) {
      res.redirect(302, `https://github.com/${REPO}/releases/latest`);
      return;
    }

    const release = await response.json();
    const dmg = release.assets?.find(
      (a: { name: string }) => a.name.endsWith("_aarch64.dmg")
    );

    if (dmg) {
      res.redirect(302, dmg.browser_download_url);
    } else {
      res.redirect(302, `https://github.com/${REPO}/releases/latest`);
    }
  } catch {
    res.redirect(302, `https://github.com/${REPO}/releases/latest`);
  }
}
