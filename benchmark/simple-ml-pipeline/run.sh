#!/bin/bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_python() {
    print_status "Checking Python installation..."
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
        print_success "Python 3 found: $(python3 --version)"
    elif command -v python &> /dev/null && python --version | grep -q "Python 3"; then
        PYTHON_CMD="python"
        print_success "Python 3 found: $(python --version)"
    else
        print_error "Python 3 is not installed. Please install Python 3.7 or higher."
        exit 1
    fi
}

create_venv() {
    print_status "Creating virtual environment..."
    
    if [ -d "ml_pipeline_env" ]; then
        print_warning "Virtual environment already exists. Removing old one..."
        rm -rf ml_pipeline_env
    fi
    
    $PYTHON_CMD -m venv ml_pipeline_env
    print_success "Virtual environment created successfully"
}

activate_venv() {
    print_status "Activating virtual environment..."
    
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        source ml_pipeline_env/Scripts/activate
    else
        source ml_pipeline_env/bin/activate
    fi
    
    print_success "Virtual environment activated"
}

install_packages() {
    print_status "Installing required Python packages..."
    
    pip install --upgrade pip
    
    pip install pandas
    pip install numpy
    pip install scikit-learn
    pip install matplotlib
    pip install seaborn
    pip install scipy
    pip install joblib
    
    print_success "All packages installed successfully"
    
    echo ""
    print_status "Installed packages:"
    pip list | grep -E "(pandas|numpy|scikit-learn|matplotlib|seaborn|scipy|joblib)"
}

check_scripts() {
    print_status "Checking for required Python scripts..."
    
    required_scripts=("data-acquisition.py" "data-processing.py" "model-training.py" )
    missing_scripts=()
    
    for script in "${required_scripts[@]}"; do
        if [ ! -f "$script" ]; then
            missing_scripts+=("$script")
        fi
    done
    
    if [ ${#missing_scripts[@]} -ne 0 ]; then
        print_error "Missing required scripts:"
        for script in "${missing_scripts[@]}"; do
            echo "  - $script"
        done
        print_error "Please ensure all Python scripts are in the current directory."
        exit 1
    fi
    
    print_success "All required scripts found"
}

run_pipeline() {
    print_status "Starting ML Pipeline execution..."
    echo ""
    
    echo "Step 1: Data Acquisition"
    python data-acquisition.py
    if [ $? -eq 0 ]; then
        print_success "Data acquisition completed"
    else
        print_error "Data acquisition failed"
        exit 1
    fi
    echo ""
    
    echo "Step 2: Data Preprocessing"
    python data-processing.py
    if [ $? -eq 0 ]; then
        print_success "Data preprocessing completed"
    else
        print_error "Data preprocessing failed"
        exit 1
    fi
    echo ""
    
    echo "Step 3: Model Training"
    python model-training.py
    if [ $? -eq 0 ]; then
        print_success "Model training completed"
    else
        print_error "Model training failed"
        exit 1
    fi
    echo ""
}

# Show results summary
show_results() {
    print_success "Pipeline execution completed successfully!"
    echo ""
}

cleanup() {
    print_status "Cleaning up..."
    if [[ "$VIRTUAL_ENV" != "" ]]; then
        deactivate
    fi
}

main() {
    echo "Starting automated ML pipeline setup and execution..."
    echo ""
    
    trap cleanup EXIT
    
    check_python
    check_scripts
    create_venv
    activate_venv
    install_packages
    run_pipeline
    show_results
    
    print_success "ML Pipeline completed successfully!"
    echo ""
    echo "To reactivate the virtual environment later, run:"
    if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        echo "  source ml_pipeline_env/Scripts/activate"
    else
        echo "  source ml_pipeline_env/bin/activate"
    fi
    echo ""
}

main "$@"