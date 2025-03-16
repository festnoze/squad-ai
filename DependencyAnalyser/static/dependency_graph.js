/**
 * Interactive Dependency Graph Visualization
 * Creates a dynamic, interactive visualization of sub-libraries and their dependencies
 */

class DependencyGraph {
  constructor(containerId, data, options = {}) {
    this.containerId = containerId;
    this.data = data;
    this.width = options.width || 800;
    this.height = options.height || 600;
    this.selectedNode = null;
    this.simulation = null;
    this.nodes = [];
    this.links = [];
    this.svg = null;
    this.nodeElements = null;
    this.linkElements = null;
    this.textElements = null;
    this.colorScale = d3.scaleSequential(d3.interpolateBlues)
      .domain([0, 10]);  // 0-10 scale for dep count
    
    // Default options with ability to override
    this.options = {
      nodeMinSize: 30,
      nodeMaxSize: 100,
      nodeActiveSizeMultiplier: 1.5,
      fontMinSize: 14,
      fontMaxSize: 20,
      fontActiveSize: 24,
      linkWidth: 1.5,
      linkActiveWidth: 2.5,
      transitionDuration: 750,
      ...options
    };

    this.init();
  }
  
  /**
   * Initialize the graph visualization
   */
  init() {
    const container = d3.select(`#${this.containerId}`);
    
    // Clear any existing content
    container.html("");
    
    // Create SVG
    this.svg = container.append("svg")
      .attr("width", this.width)
      .attr("height", this.height)
      .attr("viewBox", `0 0 ${this.width} ${this.height}`)
      .attr("preserveAspectRatio", "xMidYMid meet")
      .attr("class", "dependency-graph");
    
    // Add zoom behavior
    const zoom = d3.zoom()
      .scaleExtent([0.1, 5])
      .on("zoom", (event) => {
        this.svg.select("g").attr("transform", event.transform);
      });
    
    this.svg.call(zoom);
    
    // Create a container for all elements
    const g = this.svg.append("g");
    
    // Prepare data
    this.prepareData();
    
    // Create force simulation
    this.createSimulation();
    
    // Draw the graph
    this.draw();
  }
  
  /**
   * Prepare the data for visualization
   */
  prepareData() {
    if (!this.data || !this.data.nodes || !this.data.links) {
      console.error("Invalid data format");
      return;
    }
    
    this.nodes = this.data.nodes.map(node => ({
      ...node,
      radius: this.calculateNodeRadius(node.moduleCount || 1),
      color: this.calculateNodeColor(node.externalDepsCount || 0)
    }));
    
    this.links = this.data.links.map(link => ({
      ...link,
      source: link.source,
      target: link.target
    }));
  }
  
  /**
   * Calculate the radius of a node based on module count
   */
  calculateNodeRadius(moduleCount) {
    const { nodeMinSize, nodeMaxSize } = this.options;
    return nodeMinSize + Math.sqrt(moduleCount) * 5;
  }
  
  /**
   * Calculate the color of a node based on external dependency count
   */
  calculateNodeColor(depCount) {
    const color = this.colorScale(Math.min(depCount, 10));
    // Make color much lighter for better text visibility
    return d3.color(color).brighter(1.3).toString();
  }
  
  /**
   * Create the force simulation
   */
  createSimulation() {
    this.simulation = d3.forceSimulation(this.nodes)
      .force("link", d3.forceLink(this.links)
        .id(d => d.id)
        .distance(d => 120 + d.source.radius + d.target.radius)
      )
      .force("charge", d3.forceManyBody().strength(-200))
      .force("center", d3.forceCenter(this.width / 2, this.height / 2))
      .force("collision", d3.forceCollide().radius(d => d.radius + 10))
      .on("tick", () => this.updatePositions());
  }
  
  /**
   * Draw the graph
   */
  draw() {
    const g = this.svg.select("g");
    
    // Draw links
    this.linkElements = g.append("g")
      .attr("class", "links")
      .selectAll("line")
      .data(this.links)
      .enter()
      .append("line")
      .attr("stroke", "#aaa")
      .attr("stroke-width", this.options.linkWidth)
      .attr("marker-end", "url(#arrowhead)");
    
    // Define arrow marker
    this.svg.append("defs").append("marker")
      .attr("id", "arrowhead")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 15)
      .attr("refY", 0)
      .attr("orient", "auto")
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .append("path")
      .attr("d", "M0,-5L10,0L0,5")
      .attr("fill", "#999");
    
    // Draw nodes
    this.nodeElements = g.append("g")
      .attr("class", "nodes")
      .selectAll("circle")
      .data(this.nodes)
      .enter()
      .append("circle")
      .attr("r", d => d.radius)
      .attr("fill", d => d.color)
      .attr("stroke", d => d3.color(d.color).darker(0.5))
      .attr("stroke-width", 2)
      .on("click", (event, d) => this.handleNodeClick(d))
      .call(d3.drag()
        .on("start", this.dragStarted.bind(this))
        .on("drag", this.dragging.bind(this))
        .on("end", this.dragEnded.bind(this))
      );
    
    // Draw text labels
    this.textElements = g.append("g")
      .attr("class", "texts")
      .selectAll("text")
      .data(this.nodes)
      .enter()
      .append("text")
      .text(d => d.label)
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "middle")
      .attr("font-family", "Arial, sans-serif")
      .attr("font-weight", "bold")
      .attr("font-size", d => this.calculateFontSize(d.moduleCount || 1))
      .attr("fill", "black")
      .attr("pointer-events", "none");
    
    // Add tooltips
    this.nodeElements.append("title")
      .text(d => `${d.label}\n${d.moduleCount} modules\n${d.externalDepsCount} external dependencies`);
  }
  
  /**
   * Calculate the font size based on module count
   */
  calculateFontSize(moduleCount) {
    const { fontMinSize, fontMaxSize } = this.options;
    return Math.min(fontMinSize + Math.sqrt(moduleCount), fontMaxSize);
  }
  
  /**
   * Update the positions of all elements
   */
  updatePositions() {
    this.linkElements
      .attr("x1", d => d.source.x)
      .attr("y1", d => d.source.y)
      .attr("x2", d => d.target.x)
      .attr("y2", d => d.target.y);
    
    this.nodeElements
      .attr("cx", d => d.x)
      .attr("cy", d => d.y);
    
    this.textElements
      .attr("x", d => d.x)
      .attr("y", d => d.y);
  }
  
  /**
   * Handle node click event
   */
  handleNodeClick(d) {
    const isDeselect = this.selectedNode === d.id;
    
    // Reset all nodes first
    this.resetNodes();
    
    if (!isDeselect) {
      this.selectedNode = d.id;
      this.highlightNode(d);
    } else {
      this.selectedNode = null;
    }
  }
  
  /**
   * Highlight a node and its connections
   */
  highlightNode(d) {
    const { nodeActiveSizeMultiplier, fontActiveSize, linkActiveWidth, transitionDuration } = this.options;
    
    // Find connected links and nodes
    const connectedLinkIds = new Set();
    const connectedNodeIds = new Set([d.id]);
    
    this.links.forEach(link => {
      if (link.source.id === d.id || link.target.id === d.id) {
        connectedLinkIds.add(link.index);
        
        if (link.source.id === d.id) {
          connectedNodeIds.add(link.target.id);
        } else {
          connectedNodeIds.add(link.source.id);
        }
      }
    });
    
    // Highlight nodes
    this.nodeElements
      .transition()
      .duration(transitionDuration)
      .attr("r", node => {
        if (node.id === d.id) {
          return node.radius * nodeActiveSizeMultiplier;
        } else if (connectedNodeIds.has(node.id)) {
          return node.radius * 1.2;
        } else {
          return node.radius * 0.8;
        }
      })
      .attr("opacity", node => connectedNodeIds.has(node.id) ? 1 : 0.4);
    
    // Highlight text
    this.textElements
      .transition()
      .duration(transitionDuration)
      .attr("font-size", node => {
        if (node.id === d.id) {
          return fontActiveSize;
        } else if (connectedNodeIds.has(node.id)) {
          return this.calculateFontSize(node.moduleCount || 1);
        } else {
          return this.calculateFontSize(node.moduleCount || 1) * 0.8;
        }
      })
      .attr("opacity", node => connectedNodeIds.has(node.id) ? 1 : 0.4);
    
    // Highlight links
    this.linkElements
      .transition()
      .duration(transitionDuration)
      .attr("stroke-width", link => connectedLinkIds.has(link.index) ? linkActiveWidth : this.options.linkWidth)
      .attr("opacity", link => connectedLinkIds.has(link.index) ? 1 : 0.2);
    
    // Center view on the selected node
    const transform = d3.zoomTransform(this.svg.node());
    const scale = transform.k;
    
    this.svg.transition()
      .duration(transitionDuration)
      .call(
        d3.zoom().transform,
        d3.zoomIdentity
          .translate(this.width / 2, this.height / 2)
          .scale(scale)
          .translate(-d.x, -d.y)
      );
  }
  
  /**
   * Reset all nodes to their original state
   */
  resetNodes() {
    const { transitionDuration } = this.options;
    
    this.nodeElements
      .transition()
      .duration(transitionDuration)
      .attr("r", d => d.radius)
      .attr("opacity", 1);
    
    this.textElements
      .transition()
      .duration(transitionDuration)
      .attr("font-size", d => this.calculateFontSize(d.moduleCount || 1))
      .attr("opacity", 1);
    
    this.linkElements
      .transition()
      .duration(transitionDuration)
      .attr("stroke-width", this.options.linkWidth)
      .attr("opacity", 1);
  }
  
  /**
   * Handle drag start event
   */
  dragStarted(event, d) {
    if (!event.active) this.simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
  }
  
  /**
   * Handle dragging event
   */
  dragging(event, d) {
    d.fx = event.x;
    d.fy = event.y;
  }
  
  /**
   * Handle drag end event
   */
  dragEnded(event, d) {
    if (!event.active) this.simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
  }
  
  /**
   * Update the graph with new data
   */
  updateData(data) {
    this.data = data;
    this.selectedNode = null;
    this.prepareData();
    
    // Update simulation
    this.simulation.nodes(this.nodes);
    this.simulation.force("link").links(this.links);
    this.simulation.alpha(1).restart();
    
    // Redraw
    this.svg.select("g").remove();
    this.svg.append("g");
    this.draw();
  }
  
  /**
   * Resize the graph
   */
  resize(width, height) {
    this.width = width;
    this.height = height;
    
    this.svg
      .attr("width", width)
      .attr("height", height)
      .attr("viewBox", `0 0 ${width} ${height}`);
    
    this.simulation.force("center", d3.forceCenter(width / 2, height / 2));
    this.simulation.alpha(0.3).restart();
  }
}

/**
 * Creates a dependency graph visualization
 */
function createDependencyGraph(containerId, graphData, options = {}) {
  // Wait for DOM to be ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
      new DependencyGraph(containerId, graphData, options);
    });
  } else {
    new DependencyGraph(containerId, graphData, options);
  }
}
