// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "BRECHORISEEAdmin",
    platforms: [.iOS(.v15)],
    products: [
        .library(name: "BRECHORISEEAdmin", targets: ["App"])
    ],
    targets: [
        .target(name: "App", path: "Sources")
    ]
)
