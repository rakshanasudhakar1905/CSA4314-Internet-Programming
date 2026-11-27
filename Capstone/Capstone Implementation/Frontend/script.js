const API_BASE = "/api";
let currentQuery = "";
let chartInstance = null;

const PLATFORM_KEYS = ["amazon", "flipkart", "myntra", "meesho", "ajio"];

document.getElementById("searchInput").addEventListener("keypress", function (e) {
    if (e.key === "Enter") {
        searchProduct();
    }
});

async function searchProduct() {
    const query = document.getElementById("searchInput").value.trim();
    if (!query) return;

    currentQuery = query;
    document.getElementById("loader").classList.remove("hidden");
    document.getElementById("recommendationBanner").classList.add("hidden");
    document.getElementById("comparisonGrid").classList.add("hidden");
    document.getElementById("alertAndChartSection").classList.add("hidden");

    try {
        const response = await fetch(`${API_BASE}/compare?q=${encodeURIComponent(query)}`);
        const data = await response.json();

        if (!response.ok || data.error) {
            throw new Error(data.error || "Server returned an error.");
        }

        renderComparison(data);
        loadHistoryChart(query);
    } catch (error) {
        alert("Failed to connect to backend server. Ensure Flask is running on port 5000.");
        console.error(error);
    } finally {
        document.getElementById("loader").classList.add("hidden");
    }
}

function renderComparison(data) {
    const { platforms, recommendation } = data;

    PLATFORM_KEYS.forEach(key => {
        const item = platforms[key];
        const card = document.getElementById(`${key}Card`);
        card.classList.remove("winner");

        document.getElementById(`${key}Title`).innerText = item.title;
        document.getElementById(`${key}Price`).innerText = item.price
            ? `₹${item.price.toLocaleString("en-IN")}`
            : "Check Live Price";
        document.getElementById(`${key}Link`).href = item.url;

        const imgEl = document.getElementById(`${key}Img`);
        if (item.image) {
            imgEl.src = item.image;
            imgEl.classList.remove("hidden");
        } else {
            imgEl.classList.add("hidden");
        }
    });

    const banner = document.getElementById("recommendationBanner");
    if (recommendation) {
        const savingsText = recommendation.savings > 0
            ? ` (You save ₹${recommendation.savings.toLocaleString("en-IN")})`
            : "";
        banner.innerHTML = `
            <div>
                <strong>Lowest Price Suggested:</strong> Buy from <strong>${recommendation.best_platform}</strong> at 
                <strong>₹${recommendation.lowest_price.toLocaleString("en-IN")}</strong>${savingsText}
            </div>
            <a href="${recommendation.buy_url}" target="_blank" rel="noopener noreferrer">Order Now on ${recommendation.best_platform}</a>
        `;
        banner.classList.remove("hidden");

        const winnerKey = recommendation.best_platform.toLowerCase();
        const winnerCard = document.getElementById(`${winnerKey}Card`);
        if (winnerCard) winnerCard.classList.add("winner");
    }

    document.getElementById("comparisonGrid").classList.remove("hidden");
    document.getElementById("alertAndChartSection").classList.remove("hidden");
}

async function submitAlert(event) {
    event.preventDefault();
    const email = document.getElementById("alertEmail").value;
    const targetPrice = document.getElementById("targetPrice").value;

    const res = await fetch(`${API_BASE}/alerts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            email: email,
            product_query: currentQuery,
            target_price: targetPrice
        })
    });

    const data = await res.json();
    document.getElementById("alertStatus").innerText = data.message || data.error;
}

async function loadHistoryChart(query) {
    const res = await fetch(`${API_BASE}/history?q=${encodeURIComponent(query)}`);
    const rows = await res.json();

    const labels = rows.map(r => new Date(r.recorded_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }));

    const platformColors = {
        "Amazon": "#f59e0b",
        "Flipkart": "#2563eb",
        "Myntra": "#ec4899",
        "Meesho": "#9333ea",
        "Ajio": "#334155"
    };

    const datasets = Object.keys(platformColors).map(platformName => ({
        label: `${platformName} (₹)`,
        data: rows.map(r => r.platform === platformName ? r.price : null),
        borderColor: platformColors[platformName],
        spanGaps: true,
        tension: 0.2
    }));

    const ctx = document.getElementById("priceChart").getContext("2d");
    if (chartInstance) chartInstance.destroy();

    chartInstance = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: datasets
        }
    });
}