# Install Options

The main installer is recommended for most users.

## macOS / Linux

```sh
curl -fsSL https://raw.githubusercontent.com/fpenguin/getsubtitle/main/setup.sh -o setup.sh
sh setup.sh
```

## Windows PowerShell

```powershell
Invoke-WebRequest https://raw.githubusercontent.com/fpenguin/getsubtitle/main/setup.ps1 -OutFile setup.ps1
.\setup.ps1
```

If PowerShell blocks `.\setup.ps1`:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\setup.ps1
```

## pipx

If you already use `pipx`:

```sh
pipx install "getsubtitle[furigana,romanization-ko,romanization-zh,romanization-yue] @ git+https://github.com/fpenguin/getsubtitle.git"
```

On Windows:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
```

## Developer Checkout

```sh
git clone https://github.com/fpenguin/getsubtitle.git
cd getsubtitle
./setup.sh
```

On Windows:

```powershell
.\setup.ps1
```

The setup script creates an editable virtual environment at `./.venv`.

Activate it each session:

```sh
source .venv/bin/activate
```

On Windows:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Optional Dependencies

```sh
pip install -e ".[furigana]"
pip install -e ".[romanization-ko]"
pip install -e ".[romanization-zh]"
pip install -e ".[romanization-yue]"
pip install -e .
```

On Windows, prefix with `py -m `.

## PyPI Name

`pip install getsubtitle` does **not** install this tool. The PyPI name is held
by an older unrelated project. Use the GitHub installer or the `pipx ... @
git+...` form above.
