"""Small offline SVG field preview; no basemap or remote tiles."""

from html import escape


def field_svg(features: list[dict], selected: int) -> str:
    rings = []
    for feature in features:
        geometry = feature["geometry"]
        if geometry["type"] == "Polygon":
            rings.append([geometry["coordinates"][0]])
        else:
            rings.append([polygon[0] for polygon in geometry["coordinates"]])
    points = [point for feature_rings in rings for ring in feature_rings for point in ring]
    if not points:
        return "<p>No coordinates to display.</p>"
    west, east = min(p[0] for p in points), max(p[0] for p in points)
    south, north = min(p[1] for p in points), max(p[1] for p in points)
    dx, dy = max(east - west, 1e-9), max(north - south, 1e-9)
    shapes = []
    for i, feature_rings in enumerate(rings):
        for ring in feature_rings:
            coords = " ".join(f"{30 + (p[0]-west)/dx*640:.1f},{275 - (p[1]-south)/dy*240:.1f}"
                              for p in ring)
            fill = "#3f9463" if i == selected else "#a8b8aa"
            shapes.append(f'<polygon points="{coords}" fill="{fill}" fill-opacity="0.65" stroke="#244333" stroke-width="2"/>')
    labels = []
    for i, feature_rings in enumerate(rings):
        pts = feature_rings[0]
        cx = 30 + (sum(p[0] for p in pts) / len(pts) - west) / dx * 640
        cy = 275 - (sum(p[1] for p in pts) / len(pts) - south) / dy * 240
        name = escape(str(features[i].get("properties", {}).get("name") or f"Field {i+1}"))
        labels.append(f'<text x="{cx:.1f}" y="{cy:.1f}" text-anchor="middle" font-size="14" fill="#173422">{name}</text>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="100%" height="310" viewBox="0 0 700 310" '
            'role="img" aria-label="Field boundary sketch">'
            '<rect width="700" height="310" fill="#eef4e9" rx="12"/>'
            + "".join(shapes + labels) + '</svg><small>Boundary sketch only · no basemap or scale</small>')
