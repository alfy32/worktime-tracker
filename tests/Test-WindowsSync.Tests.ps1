BeforeAll {
    . (Join-Path $PSScriptRoot '../agents/windows/sync.ps1') -Since "1970-01-01"
}

Describe "Remove-ConsecutiveDuplicates" { }
Describe "ConvertTo-WorktimeEvents" { }
Describe "Get-Config" { }
Describe "Send-WorktimeEvents" { }
