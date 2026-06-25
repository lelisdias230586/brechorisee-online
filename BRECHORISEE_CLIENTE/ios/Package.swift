// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "BRECHORISEECliente",
    platforms: [.iOS(.v15)],
    products: [
        .library(name: "BRECHORISEECliente", targets: ["App"])
    ],
    targets: [
        .target(name: "App", path: "Sources")
    ]
)
