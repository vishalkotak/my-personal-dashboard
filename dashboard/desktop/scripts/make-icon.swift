// Turns the iPhone app's square icon into a macOS-style icon: the artwork inside Apple's
// rounded-square shape (824 px on a 1024 px canvas) with a soft drop shadow.
//
//   swift scripts/make-icon.swift <ios-icon-1024.png> <out-1024.png>
import AppKit

let args = CommandLine.arguments
guard args.count == 3, let src = NSImage(contentsOfFile: args[1])?
    .cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("usage: make-icon.swift <in.png> <out.png>\n".data(using: .utf8)!)
    exit(1)
}

let size = 1024.0, body = 824.0, radius = 185.0
let rect = CGRect(x: (size - body) / 2, y: (size - body) / 2 + 10, width: body, height: body)
let cs = CGColorSpace(name: CGColorSpace.sRGB)!
let ctx = CGContext(data: nil, width: Int(size), height: Int(size), bitsPerComponent: 8, bytesPerRow: 0,
                    space: cs, bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
let shape = CGPath(roundedRect: rect, cornerWidth: radius, cornerHeight: radius, transform: nil)

// Shadow under the tile.
ctx.saveGState()
ctx.setShadow(offset: CGSize(width: 0, height: -10), blur: 28, color: CGColor(gray: 0, alpha: 0.35))
ctx.addPath(shape)
ctx.setFillColor(CGColor(gray: 0, alpha: 1))
ctx.fillPath()
ctx.restoreGState()

// Artwork clipped to the tile.
ctx.saveGState()
ctx.addPath(shape)
ctx.clip()
ctx.draw(src, in: rect)
ctx.restoreGState()

let rep = NSBitmapImageRep(cgImage: ctx.makeImage()!)
try! rep.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: args[2]))
