// Touch ID for the lock of Passwords (plume-touchid, in Plume.app/Contents/MacOS: macOS names Plume in its dialog).
//   plume-touchid            exit 0 when this Mac can check a finger (a reader, a finger enrolled), 3 otherwise
//   plume-touchid verify R   asks for a finger with the reason R: 0 recognised, 2 cancelled, 1 not recognised
// Nothing is read or kept: macOS only answers yes or no. SIGTERM closes the dialog (the lock opened another way).
import Foundation
import LocalAuthentication

let context = LAContext()
context.localizedFallbackTitle = ""         // no « Enter password »: the session password is typed in Plume
let policy = LAPolicy.deviceOwnerAuthenticationWithBiometrics
var error: NSError?
guard context.canEvaluatePolicy(policy, error: &error) else { exit(3) }
let args = CommandLine.arguments
guard args.count > 1, args[1] == "verify" else { exit(0) }

signal(SIGTERM, SIG_IGN)
let stop = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .global())
stop.setEventHandler { context.invalidate(); exit(2) }
stop.resume()

let cancels: [LAError.Code] = [.userCancel, .systemCancel, .appCancel, .userFallback]
let done = DispatchSemaphore(value: 0)
var code: Int32 = 1
context.evaluatePolicy(policy, localizedReason: args.count > 2 ? args[2] : "Plume") { ok, failure in
    if ok {
        code = 0
    } else if let failure = failure as? LAError, cancels.contains(failure.code) {
        code = 2
    }
    done.signal()
}
done.wait()
exit(code)
