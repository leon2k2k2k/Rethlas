export async function fetchJSON(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(response.status + " " + (await response.text()));
  return response.json();
}

export function fileUrl(path, root) {
  return "/api/file?path=" + encodeURIComponent(path) +
    "&root=" + encodeURIComponent(root || "main");
}

export async function fetchFile(path, root) {
  const response = await fetch(fileUrl(path, root));
  if (!response.ok) throw new Error(response.status + " " + response.statusText);
  return response.text();
}
