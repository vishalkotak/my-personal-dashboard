// Re-render the app icon:  swift scripts/render-icon.swift HealthSync/Assets.xcassets/AppIcon.appiconset
import AppKit
import CoreGraphics

// Renders the HealthSync app icon (1024×1024) in three appearances: light, dark, tinted.
let size: CGFloat = 1024
let outDir = CommandLine.arguments[1]

enum Style { case light, dark, tinted }

func color(_ hex: UInt32, _ a: CGFloat = 1) -> CGColor {
    CGColor(srgbRed: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
            blue: CGFloat(hex & 0xFF) / 255, alpha: a)
}

/// Classic heart, centred at (cx, cy), width w. Flipped coordinates: y grows upward.
func heartPath(cx: CGFloat, cy: CGFloat, w: CGFloat) -> CGPath {
    let p = CGMutablePath()
    let h = w * 0.92
    let top = cy + h * 0.36, bottom = cy - h * 0.52
    p.move(to: CGPoint(x: cx, y: bottom))
    p.addCurve(to: CGPoint(x: cx - w * 0.5, y: top - h * 0.10),
               control1: CGPoint(x: cx - w * 0.18, y: bottom + h * 0.20),
               control2: CGPoint(x: cx - w * 0.52, y: cy - h * 0.10))
    p.addCurve(to: CGPoint(x: cx, y: top - h * 0.02),
               control1: CGPoint(x: cx - w * 0.48, y: top + h * 0.22),
               control2: CGPoint(x: cx - w * 0.08, y: top + h * 0.24))
    p.addCurve(to: CGPoint(x: cx + w * 0.5, y: top - h * 0.10),
               control1: CGPoint(x: cx + w * 0.08, y: top + h * 0.24),
               control2: CGPoint(x: cx + w * 0.48, y: top + h * 0.22))
    p.addCurve(to: CGPoint(x: cx, y: bottom),
               control1: CGPoint(x: cx + w * 0.52, y: cy - h * 0.10),
               control2: CGPoint(x: cx + w * 0.18, y: bottom + h * 0.20))
    p.closeSubpath()
    return p
}

/// Two arcs circling the heart, each ending in an arrowhead (the "sync" symbol).
func drawSyncArrows(_ ctx: CGContext, c: CGPoint, r: CGFloat, line: CGFloat, stroke: CGColor) {
    ctx.setStrokeColor(stroke)
    ctx.setFillColor(stroke)
    ctx.setLineWidth(line)
    ctx.setLineCap(.round)
    let sweep: CGFloat = .pi * 0.72          // each arc covers 130°, leaving room for the arrowheads
    let headLength = line * 1.9, headHalfWidth = line * 1.15
    for start in [CGFloat.pi * 0.95, CGFloat.pi * 1.95] {   // two arcs, 180° apart
        let end = start - sweep                               // clockwise = decreasing angle
        ctx.addArc(center: c, radius: r, startAngle: start, endAngle: end, clockwise: true)
        ctx.strokePath()

        // Arrowhead: base centred on the arc's end, tip pushed forward along the direction of travel.
        let endPoint = CGPoint(x: c.x + r * cos(end), y: c.y + r * sin(end))
        let tangent = CGPoint(x: sin(end), y: -cos(end))      // clockwise direction of travel
        let radial = CGPoint(x: cos(end), y: sin(end))
        // Bend the tip slightly inward so the head follows the curve instead of shooting off it.
        let bend = headLength / r * 0.5
        let tipAngle = end - bend
        let tipDir = CGPoint(x: sin(tipAngle), y: -cos(tipAngle))
        let tip = CGPoint(x: endPoint.x + tipDir.x * headLength, y: endPoint.y + tipDir.y * headLength)
        _ = tangent
        ctx.move(to: tip)
        ctx.addLine(to: CGPoint(x: endPoint.x + radial.x * headHalfWidth, y: endPoint.y + radial.y * headHalfWidth))
        ctx.addLine(to: CGPoint(x: endPoint.x - radial.x * headHalfWidth, y: endPoint.y - radial.y * headHalfWidth))
        ctx.closePath()
        ctx.fillPath()
    }
}

func render(_ style: Style, to file: String) {
    let cs = CGColorSpace(name: CGColorSpace.sRGB)!
    let ctx = CGContext(data: nil, width: Int(size), height: Int(size), bitsPerComponent: 8, bytesPerRow: 0,
                        space: cs, bitmapInfo: (style == .light ? CGImageAlphaInfo.noneSkipLast : CGImageAlphaInfo.premultipliedLast).rawValue)!
    let full = CGRect(x: 0, y: 0, width: size, height: size)
    let center = CGPoint(x: size / 2, y: size / 2)

    // Background: light = warm gradient; dark/tinted = transparent (iOS supplies the backdrop).
    if style == .light {
        let g = CGGradient(colorsSpace: cs, colors: [color(0xFF7A59), color(0xFF3B6B), color(0xD6246E)] as CFArray,
                           locations: [0, 0.55, 1])!
        ctx.drawLinearGradient(g, start: CGPoint(x: 0, y: size), end: CGPoint(x: size, y: 0), options: [])
        // soft highlight top-left for depth
        let glow = CGGradient(colorsSpace: cs, colors: [color(0xFFFFFF, 0.22), color(0xFFFFFF, 0)] as CFArray, locations: [0, 1])!
        ctx.drawRadialGradient(glow, startCenter: CGPoint(x: size * 0.28, y: size * 0.80), startRadius: 0,
                               endCenter: CGPoint(x: size * 0.28, y: size * 0.80), endRadius: size * 0.6, options: [])
    } else {
        ctx.clear(full)
    }

    let heart = heartPath(cx: center.x, cy: center.y - 6, w: size * 0.40)
    let ringR = size * 0.335, ringLine = size * 0.052

    switch style {
    case .light:
        // subtle shadow under the glyphs
        ctx.saveGState()
        ctx.setShadow(offset: CGSize(width: 0, height: -14), blur: 36, color: color(0x7A0A33, 0.35))
        ctx.beginTransparencyLayer(auxiliaryInfo: nil)   // one shadow for the whole glyph, no seams
        ctx.addPath(heart); ctx.setFillColor(color(0xFFFFFF)); ctx.fillPath()
        drawSyncArrows(ctx, c: center, r: ringR, line: ringLine, stroke: color(0xFFFFFF))
        ctx.endTransparencyLayer()
        ctx.restoreGState()
    case .dark:
        // glyphs carry the colour: gradient heart, warm ring
        ctx.saveGState()
        ctx.addPath(heart); ctx.clip()
        let g = CGGradient(colorsSpace: cs, colors: [color(0xFF8A65), color(0xFF3B6B)] as CFArray, locations: [0, 1])!
        ctx.drawLinearGradient(g, start: CGPoint(x: 0, y: size * 0.7), end: CGPoint(x: size, y: size * 0.3), options: [])
        ctx.restoreGState()
        drawSyncArrows(ctx, c: center, r: ringR, line: ringLine, stroke: color(0xFF6F61))
    case .tinted:
        // grayscale; iOS applies the user's tint. Heart brightest, ring a step dimmer.
        ctx.addPath(heart); ctx.setFillColor(color(0xFFFFFF)); ctx.fillPath()
        drawSyncArrows(ctx, c: center, r: ringR, line: ringLine, stroke: color(0xBFBFBF))
    }

    let image = ctx.makeImage()!
    let rep = NSBitmapImageRep(cgImage: image)
    try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: file))
}

render(.light, to: "\(outDir)/AppIcon.png")
render(.dark, to: "\(outDir)/AppIcon-Dark.png")
render(.tinted, to: "\(outDir)/AppIcon-Tinted.png")
print("rendered to \(outDir)")
