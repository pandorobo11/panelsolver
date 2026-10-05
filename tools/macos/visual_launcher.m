// Keep the bundle executable alive while CPython runs the ordinary GUI script.
// Replacing it with exec(python) can leave NSRunningApplication's PID at -1,
// preventing external accessibility clients from identifying the application.
#import <Foundation/Foundation.h>
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int fail(NSString *message) {
    fprintf(stderr, "Panel Solver visual launcher: %s\n", message.UTF8String);
    return 1;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        NSString *root = NSBundle.mainBundle.bundlePath;
        for (int i = 0; i < 3; ++i)
            root = root.stringByDeletingLastPathComponent;
        NSString *script = [root stringByAppendingPathComponent:@"scripts/gui_visual_smoke.py"];
        NSString *probe = [root stringByAppendingPathComponent:@"scripts/macos_visual_runtime.py"];
        NSFileManager *files = NSFileManager.defaultManager;
        if (![files fileExistsAtPath:script] || ![files fileExistsAtPath:probe])
            return fail(@"Keep this app in its checkout's tools/macos directory.");
        if (chdir(root.fileSystemRepresentation) != 0)
            return fail(@"Cannot enter the checkout directory.");

        // Preserve the previous launcher's normal-display and uv lookup policy.
        unsetenv("QT_QPA_PLATFORM");
        unsetenv("PYVISTA_OFF_SCREEN");
        const char *oldPath = getenv("PATH");
        NSString *path = [@"/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:"
            stringByAppendingString:oldPath ? @(oldPath) : @""];
        setenv("PATH", path.UTF8String, 1);

        NSString *python = [root stringByAppendingPathComponent:@".venv/bin/python"];
        NSTask *task = [[NSTask alloc] init];
        if ([files isExecutableFileAtPath:python]) {
            task.executableURL = [NSURL fileURLWithPath:python];
            task.arguments = @[@"-I", probe];
        } else {
            task.executableURL = [NSURL fileURLWithPath:@"/usr/bin/env"];
            task.arguments = @[@"uv", @"run", @"--locked", @"python", @"-I", probe];
        }
        task.currentDirectoryURL = [NSURL fileURLWithPath:root];
        NSPipe *output = [NSPipe pipe];
        task.standardOutput = output;
        task.standardError = NSFileHandle.fileHandleWithStandardError;
        NSError *error = nil;
        if (![task launchAndReturnError:&error])
            return fail([@"Cannot discover Python: " stringByAppendingString:error.localizedDescription]);
        NSData *data = [output.fileHandleForReading readDataToEndOfFile];
        [task waitUntilExit];
        if (task.terminationStatus != 0)
            return fail(@"Python discovery failed. Prepare the locked environment with uv sync.");
        id info = [NSJSONSerialization JSONObjectWithData:data options:0 error:&error];
        if (![info isKindOfClass:NSDictionary.class]
            || ![info[@"executable"] isKindOfClass:NSString.class]
            || ![info[@"library"] isKindOfClass:NSString.class])
            return fail(@"Python discovery returned invalid runtime information.");
        python = info[@"executable"];
        NSString *library = info[@"library"];
        if (![files isExecutableFileAtPath:python] || ![files fileExistsAtPath:library])
            return fail(@"The discovered Python runtime is no longer available.");

        void *handle = dlopen(library.fileSystemRepresentation, RTLD_NOW | RTLD_GLOBAL);
        if (!handle)
            return fail([NSString stringWithFormat:@"Cannot load Python: %s", dlerror()]);
        int (*pythonMain)(int, char **) = (int (*)(int, char **))dlsym(handle, "Py_BytesMain");
        if (!pythonMain)
            return fail(@"The Python library does not export Py_BytesMain.");

        char **pythonArgs = calloc((size_t)argc + 2, sizeof(char *));
        if (!pythonArgs)
            return fail(@"Cannot allocate Python arguments.");
        // CPython uses argv[0] for venv discovery and sys.executable. Spawned
        // workers must launch that interpreter, not recursively open this app.
        pythonArgs[0] = (char *)python.fileSystemRepresentation;
        pythonArgs[1] = (char *)script.fileSystemRepresentation;
        int count = 2;
        for (int i = 1; i < argc; ++i) {
            if (strncmp(argv[i], "-psn_", 5) != 0)
                pythonArgs[count++] = argv[i];
        }
        int status = pythonMain(count, pythonArgs);
        free(pythonArgs);
        // Do not dlclose: extension-module/static destructors may still use it.
        return status;
    }
}
