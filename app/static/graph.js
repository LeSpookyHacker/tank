/* D3 v7 force-directed graph renderer.
 *
 * Usage:
 *   renderGraph(containerId, apiUrl, options)
 *
 * containerId: id of the container div
 * apiUrl:      the /api/entities-graph?... URL to fetch
 * options:     { width, height, onNodeClick }
 */
function renderGraph(containerId, apiUrl, options) {
  options = options || {};
  var root = document.getElementById(containerId);
  if (!root) return;

  // D3 guard — may still be loading (deferred).
  if (!window.d3) {
    setTimeout(function() { renderGraph(containerId, apiUrl, options); }, 50);
    return;
  }

  var W = options.width  || root.clientWidth  || 800;
  var H = options.height || options.heightPx  || 520;

  var TYPE_COLOR = {
    Service:      '#5cd7a0',
    Repo:         '#74c0ff',
    Person:       '#f0c674',
    DataStore:    '#ff6e7e',
    CloudAccount: '#b48eff',
    Vendor:       '#ffa500',
    Control:      '#5cd7a0',
    Policy:       '#9aa1ab',
    Runbook:      '#74c0ff',
    Endpoint:     '#ff6e7e',
  };
  function nodeColor(type) { return TYPE_COLOR[type] || '#9aa1ab'; }

  root.innerHTML = '<div style="color:var(--text-mute);padding:1.5rem">Loading graph…</div>';

  fetch(apiUrl)
    .then(function(r) { return r.json(); })
    .then(function(g) { _draw(g); })
    .catch(function(e) {
      root.innerHTML = '<div style="color:var(--text-mute);padding:1.5rem">Graph unavailable: ' + e.message + '</div>';
    });

  function _draw(g) {
    if (!g.nodes || !g.nodes.length) {
      root.innerHTML = '<div style="color:var(--text-mute);padding:1.5rem">No entities yet. Ingest some documents to populate the knowledge graph.</div>';
      return;
    }

    root.innerHTML = '';

    var deg = {};
    g.nodes.forEach(function(n) { deg[n.id] = 0; });
    g.edges.forEach(function(e) {
      deg[e.src_id] = (deg[e.src_id] || 0) + 1;
      deg[e.dst_id] = (deg[e.dst_id] || 0) + 1;
    });

    var svg = d3.select(root).append('svg')
      .attr('width', '100%')
      .attr('height', H)
      .style('background', 'var(--bg)')
      .style('border-radius', '10px')
      .style('border', '1px solid var(--border-soft)');

    var g_el = svg.append('g');

    // Zoom + pan
    var zoom = d3.zoom()
      .scaleExtent([0.1, 6])
      .on('zoom', function(event) { g_el.attr('transform', event.transform); });
    svg.call(zoom);

    // Arrow markers for directed edges
    svg.append('defs').selectAll('marker')
      .data(['arrow'])
      .join('marker')
        .attr('id', 'arrow')
        .attr('viewBox', '0 -5 10 10')
        .attr('refX', 20)
        .attr('refY', 0)
        .attr('markerWidth', 6)
        .attr('markerHeight', 6)
        .attr('orient', 'auto')
      .append('path')
        .attr('d', 'M0,-5L10,0L0,5')
        .attr('fill', '#3d4455');

    // D3 forceLink needs source/target keys; API returns src_id/dst_id — map them.
    var simLinks = g.edges.map(function(e) {
      return { source: e.src_id, target: e.dst_id, kind: e.kind };
    });

    var links = g_el.append('g').attr('class', 'links')
      .selectAll('line')
      .data(simLinks)
      .join('line')
        .attr('stroke', '#3d4455')
        .attr('stroke-width', 1.2)
        .attr('marker-end', 'url(#arrow)');

    var nodeR = function(d) { return Math.max(7, Math.min(18, 7 + Math.sqrt(deg[d.id] || 0) * 2.5)); };

    var nodes = g_el.append('g').attr('class', 'nodes')
      .selectAll('g')
      .data(g.nodes)
      .join('g')
        .attr('class', 'node')
        .style('cursor', 'pointer')
        .call(d3.drag()
          .on('start', function(event, d) {
            if (!event.active) sim.alphaTarget(0.3).restart();
            d.fx = d.x; d.fy = d.y;
          })
          .on('drag', function(event, d) {
            d.fx = event.x; d.fy = event.y;
          })
          .on('end', function(event, d) {
            if (!event.active) sim.alphaTarget(0);
            d.fx = null; d.fy = null;
          })
        );

    nodes.append('circle')
      .attr('r', nodeR)
      .attr('fill', function(d) { return nodeColor(d.type); })
      .attr('fill-opacity', 0.9)
      .attr('stroke', '#0c0e12')
      .attr('stroke-width', 1.5);

    nodes.append('text')
      .attr('x', function(d) { return nodeR(d) + 5; })
      .attr('y', 4)
      .attr('font-size', '11px')
      .attr('fill', '#c8ccd6')
      .attr('pointer-events', 'none')
      .text(function(d) { return d.name.length > 24 ? d.name.slice(0, 22) + '…' : d.name; });

    // Hover: highlight connected nodes, dim others
    nodes.on('mouseover', function(event, d) {
      var connected = new Set([d.id]);
      g.edges.forEach(function(e) {
        if (e.src_id === d.id) connected.add(e.dst_id);
        if (e.dst_id === d.id) connected.add(e.src_id);
      });
      nodes.selectAll('circle').style('opacity', function(n) { return connected.has(n.id) ? 1 : 0.15; });
      nodes.selectAll('text').style('opacity', function(n) { return connected.has(n.id) ? 1 : 0.1; });
      links.style('opacity', function(e) {
        var sid = (e.source && e.source.id) ? e.source.id : e.source;
        var tid = (e.target && e.target.id) ? e.target.id : e.target;
        return (sid === d.id || tid === d.id) ? 1 : 0.05;
      });
    });
    nodes.on('mouseout', function() {
      nodes.selectAll('circle').style('opacity', 1);
      nodes.selectAll('text').style('opacity', 1);
      links.style('opacity', 0.7);
    });

    // Click: navigate or custom handler
    nodes.on('click', function(event, d) {
      if (options.onNodeClick) { options.onNodeClick(d); return; }
      window.location = '/entities/' + d.id;
    });

    // Tooltip
    var tooltip = d3.select(root).append('div')
      .style('position', 'absolute')
      .style('background', 'var(--bg-elevated)')
      .style('border', '1px solid var(--border)')
      .style('border-radius', '6px')
      .style('padding', '0.4rem 0.75rem')
      .style('font-size', '0.8rem')
      .style('pointer-events', 'none')
      .style('display', 'none')
      .style('z-index', '10');

    nodes.on('mouseover.tip', function(event, d) {
      tooltip.style('display', 'block')
        .html('<strong>' + d.name + '</strong> <span style="color:var(--text-mute)">' + d.type + '</span>');
    }).on('mousemove.tip', function(event) {
      var rect = root.getBoundingClientRect();
      tooltip.style('left', (event.clientX - rect.left + 12) + 'px')
             .style('top',  (event.clientY - rect.top  + 12) + 'px');
    }).on('mouseout.tip', function() {
      tooltip.style('display', 'none');
    });

    var sim = d3.forceSimulation(g.nodes)
      .force('link', d3.forceLink(simLinks)
        .id(function(d) { return d.id; })
        .distance(100).strength(0.4))
      .force('charge', d3.forceManyBody().strength(-220))
      .force('center', d3.forceCenter(W / 2, H / 2))
      .force('collision', d3.forceCollide().radius(function(d) { return nodeR(d) + 6; }))
      .on('tick', function() {
        links
          .attr('x1', function(d) { return d.source.x; })
          .attr('y1', function(d) { return d.source.y; })
          .attr('x2', function(d) { return d.target.x; })
          .attr('y2', function(d) { return d.target.y; });
        nodes.attr('transform', function(d) { return 'translate(' + d.x + ',' + d.y + ')'; });
      });

    links.style('opacity', 0.7);

    // Initial fit-to-view zoom after simulation settles
    sim.on('end', function() {
      var bbox = g_el.node().getBBox();
      if (bbox.width > 0 && bbox.height > 0) {
        var pad = 40;
        var scale = Math.min((W - pad*2) / bbox.width, (H - pad*2) / bbox.height, 2);
        var tx = W/2 - scale * (bbox.x + bbox.width/2);
        var ty = H/2 - scale * (bbox.y + bbox.height/2);
        svg.call(zoom.transform, d3.zoomIdentity.translate(tx, ty).scale(scale));
      }
    });
  }
}

// Legacy compat shim — the old API was renderGraph(type, depth).
// entities.html calls renderGraph("Service", 2) — detect and reroute.
(function() {
  var _orig = renderGraph;
  window.renderGraph = function(a, b, c) {
    if (typeof a === 'string' && typeof b === 'number' && c === undefined) {
      // Old call: renderGraph("Service", 2)
      _orig('entity-graph', '/api/entities-graph?type=' + encodeURIComponent(a) + '&depth=' + b, {});
    } else {
      _orig(a, b, c);
    }
  };
})();
