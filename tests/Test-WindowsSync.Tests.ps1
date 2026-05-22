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
Describe "ConvertTo-WorktimeEvents" { }
Describe "Get-Config" { }
Describe "Send-WorktimeEvents" { }
