param([string]$ExePath)

$subj = 'CN=SecureLoader-Local'

$cert = Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert |
    Where-Object { $_.Subject -eq $subj } |
    Select-Object -First 1

if (-not $cert) {
    Write-Host 'Creating self-signed code-signing certificate...'
    $cert = New-SelfSignedCertificate `
        -Type CodeSigningCert `
        -Subject $subj `
        -CertStoreLocation Cert:\CurrentUser\My `
        -NotAfter (Get-Date).AddYears(5)

    # Trust the cert locally so SmartScreen accepts it on this machine
    $root = New-Object System.Security.Cryptography.X509Certificates.X509Store('Root', 'CurrentUser')
    $root.Open('ReadWrite')
    $root.Add($cert)
    $root.Close()

    $pub = New-Object System.Security.Cryptography.X509Certificates.X509Store('TrustedPublisher', 'CurrentUser')
    $pub.Open('ReadWrite')
    $pub.Add($cert)
    $pub.Close()

    Write-Host 'Certificate created and trusted locally.'
} else {
    Write-Host "Reusing existing certificate ($($cert.Thumbprint))."
}

# Try with a public timestamp server (needs internet); fall back without
$r = Set-AuthenticodeSignature $ExePath -Certificate $cert `
    -TimestampServer 'http://timestamp.digicert.com' -ErrorAction SilentlyContinue
if (-not $r -or $r.Status -ne 'Valid') {
    Write-Host 'Timestamp server unreachable, signing without timestamp...'
    $r = Set-AuthenticodeSignature $ExePath -Certificate $cert
}

if ($r.Status -eq 'Valid') {
    Write-Host "Signed OK: $ExePath"
} else {
    Write-Host "WARNING: signing status: $($r.Status)"
    exit 1
}
