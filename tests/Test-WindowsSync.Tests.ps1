BeforeAll {
    . (Join-Path $PSScriptRoot '../agents/windows/sync.ps1') -Since "1970-01-01"
}

Describe "Remove-ConsecutiveDuplicates" {
    It "returns empty for empty input" {
        Remove-ConsecutiveDuplicates @() | Should -BeNullOrEmpty
    }

    It "passes through a single event unchanged" {
        $events = @(@{ timestamp = "2026-05-22T09:00:00"; action = "login" })
        $result = Remove-ConsecutiveDuplicates $events
        $result.Count | Should -Be 1
        $result[0].action | Should -Be "login"
    }

    It "removes consecutive duplicate actions" {
        $events = @(
            @{ timestamp = "2026-05-22T09:00:00"; action = "login" },
            @{ timestamp = "2026-05-22T09:00:01"; action = "login" },
            @{ timestamp = "2026-05-22T17:00:00"; action = "logout" }
        )
        $result = Remove-ConsecutiveDuplicates $events
        $result.Count | Should -Be 2
        $result[0].action | Should -Be "login"
        $result[1].action | Should -Be "logout"
    }

    It "keeps non-consecutive same actions" {
        $events = @(
            @{ timestamp = "2026-05-22T09:00:00"; action = "login" },
            @{ timestamp = "2026-05-22T12:00:00"; action = "logout" },
            @{ timestamp = "2026-05-22T13:00:00"; action = "login" },
            @{ timestamp = "2026-05-22T17:00:00"; action = "logout" }
        )
        $result = Remove-ConsecutiveDuplicates $events
        $result.Count | Should -Be 4
    }

    It "keeps the first event in a consecutive run" {
        $events = @(
            @{ timestamp = "2026-05-22T09:00:00"; action = "logout" },
            @{ timestamp = "2026-05-22T09:00:01"; action = "logout" },
            @{ timestamp = "2026-05-22T09:00:02"; action = "logout" }
        )
        $result = Remove-ConsecutiveDuplicates $events
        $result.Count | Should -Be 1
        $result[0].timestamp | Should -Be "2026-05-22T09:00:00"
    }
}
Describe "ConvertTo-WorktimeEvents" {
    It "maps event 4624 to login" {
        $raw = @([PSCustomObject]@{ Id = 4624; TimeCreated = [datetime]"2026-05-22T09:00:00" })
        (ConvertTo-WorktimeEvents $raw)[0].action | Should -Be "login"
    }

    It "maps event 4801 to login" {
        $raw = @([PSCustomObject]@{ Id = 4801; TimeCreated = [datetime]"2026-05-22T09:00:00" })
        (ConvertTo-WorktimeEvents $raw)[0].action | Should -Be "login"
    }

    It "maps event 4634 to logout" {
        $raw = @([PSCustomObject]@{ Id = 4634; TimeCreated = [datetime]"2026-05-22T17:00:00" })
        (ConvertTo-WorktimeEvents $raw)[0].action | Should -Be "logout"
    }

    It "maps event 4647 to logout" {
        $raw = @([PSCustomObject]@{ Id = 4647; TimeCreated = [datetime]"2026-05-22T17:00:00" })
        (ConvertTo-WorktimeEvents $raw)[0].action | Should -Be "logout"
    }

    It "maps event 4800 to logout" {
        $raw = @([PSCustomObject]@{ Id = 4800; TimeCreated = [datetime]"2026-05-22T12:00:00" })
        (ConvertTo-WorktimeEvents $raw)[0].action | Should -Be "logout"
    }

    It "maps event 1074 to logout" {
        $raw = @([PSCustomObject]@{ Id = 1074; TimeCreated = [datetime]"2026-05-22T17:00:00" })
        (ConvertTo-WorktimeEvents $raw)[0].action | Should -Be "logout"
    }

    It "maps event 6006 to logout" {
        $raw = @([PSCustomObject]@{ Id = 6006; TimeCreated = [datetime]"2026-05-22T17:00:00" })
        (ConvertTo-WorktimeEvents $raw)[0].action | Should -Be "logout"
    }

    It "formats timestamp as yyyy-MM-ddTHH:mm:ss" {
        $raw = @([PSCustomObject]@{ Id = 4624; TimeCreated = [datetime]"2026-05-22T09:05:30" })
        (ConvertTo-WorktimeEvents $raw)[0].timestamp | Should -Be "2026-05-22T09:05:30"
    }

    It "sorts output by timestamp ascending" {
        $raw = @(
            [PSCustomObject]@{ Id = 4634; TimeCreated = [datetime]"2026-05-22T17:00:00" },
            [PSCustomObject]@{ Id = 4624; TimeCreated = [datetime]"2026-05-22T09:00:00" }
        )
        $result = ConvertTo-WorktimeEvents $raw
        $result[0].timestamp | Should -Be "2026-05-22T09:00:00"
        $result[1].timestamp | Should -Be "2026-05-22T17:00:00"
    }

    It "ignores unknown event IDs" {
        $raw = @([PSCustomObject]@{ Id = 9999; TimeCreated = [datetime]"2026-05-22T09:00:00" })
        ConvertTo-WorktimeEvents $raw | Should -BeNullOrEmpty
    }

    It "returns empty for empty input" {
        ConvertTo-WorktimeEvents @() | Should -BeNullOrEmpty
    }
}
Describe "Get-Config" {
    BeforeEach {
        Remove-Item Env:\WORKTIME_SERVER_URL   -ErrorAction SilentlyContinue
        Remove-Item Env:\WORKTIME_COMPUTER_NAME -ErrorAction SilentlyContinue
    }

    It "reads serverUrl and computerName from config file" {
        $tmp = Join-Path $TestDrive "config.json"
        '{"serverUrl":"http://192.168.0.125:8000","computerName":"windows"}' | Set-Content $tmp
        $result = Get-Config -ConfigPath $tmp
        $result.serverUrl    | Should -Be "http://192.168.0.125:8000"
        $result.computerName | Should -Be "windows"
    }

    It "strips trailing slash from serverUrl" {
        $tmp = Join-Path $TestDrive "config.json"
        '{"serverUrl":"http://192.168.0.125:8000/","computerName":"windows"}' | Set-Content $tmp
        $result = Get-Config -ConfigPath $tmp
        $result.serverUrl | Should -Be "http://192.168.0.125:8000"
    }

    It "reads from environment variables when config file is absent" {
        $env:WORKTIME_SERVER_URL    = "http://10.0.0.1:8000"
        $env:WORKTIME_COMPUTER_NAME = "mypc"
        $result = Get-Config -ConfigPath (Join-Path $TestDrive "missing.json")
        $result.serverUrl    | Should -Be "http://10.0.0.1:8000"
        $result.computerName | Should -Be "mypc"
    }

    It "throws when serverUrl is not set anywhere" {
        { Get-Config -ConfigPath (Join-Path $TestDrive "missing.json") } | Should -Throw
    }
}
Describe "Send-WorktimeEvents" {
    It "POSTs to /api/sync with correct payload" {
        Mock Invoke-RestMethod {
            $script:capturedUri  = $Uri
            $script:capturedBody = $Body | ConvertFrom-Json
            return [PSCustomObject]@{ inserted = 2; skipped = 0 }
        }
        $events = @(
            @{ timestamp = "2026-05-22T09:00:00"; action = "login" },
            @{ timestamp = "2026-05-22T17:00:00"; action = "logout" }
        )
        Send-WorktimeEvents -ServerUrl "http://server:8000" -ComputerName "mypc" -Events $events
        $script:capturedUri              | Should -Be "http://server:8000/api/sync"
        $script:capturedBody.computer    | Should -Be "mypc"
        $script:capturedBody.events.Count | Should -Be 2
    }

    It "returns inserted and skipped counts" {
        Mock Invoke-RestMethod { return [PSCustomObject]@{ inserted = 1; skipped = 3 } }
        $result = Send-WorktimeEvents -ServerUrl "http://server:8000" -ComputerName "mypc" `
            -Events @(@{ timestamp = "2026-05-22T09:00:00"; action = "login" })
        $result.inserted | Should -Be 1
        $result.skipped  | Should -Be 3
    }

    It "throws on connection error" {
        Mock Invoke-RestMethod { throw [System.Net.WebException]::new("Connection refused") }
        {
            Send-WorktimeEvents -ServerUrl "http://server:8000" -ComputerName "mypc" `
                -Events @(@{ timestamp = "2026-05-22T09:00:00"; action = "login" })
        } | Should -Throw
    }
}
