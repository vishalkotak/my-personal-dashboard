import Foundation

/// Values come from Config/Secrets.xcconfig (gitignored) → Info.plist → here,
/// so nothing project-specific lives in source control.
///
/// The publishable key is designed to be public: Row-Level Security is what protects the data.
/// NEVER put the secret / service_role key in the app — it bypasses RLS entirely.
enum Config {
    static let supabaseURL: URL = {
        guard let string = value(for: "SupabaseURL"), let url = URL(string: string), url.scheme == "https" else {
            fatalError("SupabaseURL missing or not https — copy Config/Secrets.example.xcconfig to Config/Secrets.xcconfig")
        }
        return url
    }()

    static let supabasePublishableKey: String = {
        guard let key = value(for: "SupabasePublishableKey"), !key.contains("REPLACE_ME") else {
            fatalError("SupabasePublishableKey missing — copy Config/Secrets.example.xcconfig to Config/Secrets.xcconfig")
        }
        precondition(!key.hasPrefix("sb_secret_"), "Refusing to run with a Supabase SECRET key in the app")
        return key
    }()

    private static func value(for key: String) -> String? {
        (Bundle.main.object(forInfoDictionaryKey: key) as? String).flatMap { $0.isEmpty ? nil : $0 }
    }
}
