require 'json'
module Resultats
  ROOT = File.expand_path('..', __dir__)
  def self.settings
    values = {}
    path = File.join(ROOT, '.env')
    if File.exist?(path)
      File.foreach(path) do |line|
        line = line.strip
        next if line.empty? || line.start_with?('#')
        key, value = line.split('=', 2)
        raise 'Invalid .env line; use KEY=value without shell syntax' unless key.match?(/\A[A-Z_]+\z/) && value
        values[key] = value
      end
    end
    values.merge(ENV.to_h)
  end
  def self.inventory(env = settings)
    count = Integer(env.fetch('NB_APP', '2'))
    octet = Integer(env.fetch('NETWORK_OCTET', '56'))
    raise 'NB_APP must be between 2 and 8' unless (2..8).cover?(count)
    raise 'NETWORK_OCTET must be between 56 and 63' unless (56..63).cover?(octet)
    prefix = "192.168.#{octet}"
    nodes = [{name: 'bdd1', role: 'primary', ip: "#{prefix}.31", memory: 768},
             {name: 'bdd2', role: 'replica', ip: "#{prefix}.32", memory: 768}]
    count.times { |i| nodes << {name: "app#{i+1}", role: 'app', ip: "#{prefix}.#{21+i}", memory: 512} }
    nodes << {name: 'lb1', role: 'lb', ip: "#{prefix}.11", memory: 512}
    {group: 10, subnet: "#{prefix}.0/24", nodes: nodes, cache_enabled: env.fetch('CACHE_ENABLED', '1') == '1'}
  end
end
puts JSON.pretty_generate(Resultats.inventory) if $PROGRAM_NAME == __FILE__
