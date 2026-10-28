# frozen_string_literal: true

# This plugin's tests, run with `trmnlp test` (add `--report report` for a page of every screen it drew).
# Docs: https://github.com/usetrmnl/trmnlp#testing-plugins
RSpec.describe 'Programme TV' do
  # The relay's files for Wednesday 2026-10-28, from midnight to 06:00 the next day (relay/build.py --hours 30
  # --only: the TNT, Arte Belgique and Maison & Travaux, the largest file), moved by whole days to today, so "now"
  # always falls on the fixtures' first day.
  FIXTURES = File.join(__dir__, 'fixtures', 'c')
  TNT = %w[TF1.fr France2.fr France3.fr CanalPlus.fr France5.fr M6.fr Arte.fr W9.fr TMC.fr NT1.fr
           LaChaineParlementaire.fr France4.fr BFMTV.fr CNews.fr CStar.fr Gulli.fr T18.fr NOVO19.fr TF1SeriesFilms.fr
           LEquipe21.fr 6ter.fr Numero23.fr RMCDecouverte.fr Cherie25.fr LCI.fr FranceInfo.fr ParisPremiere.fr
           CanalPlusSport.fr CanalPlusCinema.fr PlanetePlus.fr].freeze

  def channel_file(id)
    data = JSON.parse(File.read(File.join(FIXTURES, "#{id}.json")))
    shift = ((Time.now.to_i - data['generated']) / 86_400) * 86_400
    data['generated'] += shift
    data['programmes'].each { it[0] += shift; it[1] += shift }
    data
  end

  let(:mocks) do
    { 'https://rivallinkil.github.io/trmnl-tv-schedule/c/*' => ->(request) { { json: channel_file(File.basename(request[:url], '.json')) } } }
  end

  let(:custom_fields) { { 'channels' => %w[TF1.fr France2.fr France3.fr CanalPlus.fr France5.fr M6.fr Arte.fr] } }

  # Every view on TRMNL's devices, a failing API and every select option, checked for page errors and leaked values.
  it_behaves_like 'a publishable recipe'

  def transformed(fields) = trmnl.transform(mocks:, custom_fields: custom_fields.merge(fields)).data

  def requested(fields) = trmnl.transform(mocks:, custom_fields: fields).requests.map { File.basename(it[:url], '.json') }

  describe 'polling' do
    it 'asks for one file per chosen channel, in order' do
      expect(requested('channels' => %w[Arte.fr TF1.fr])).to eq(%w[Arte.fr TF1.fr])
    end

    it 'asks for 10 channels at most' do
      expect(requested('channels' => TNT)).to eq(TNT.first(10))
    end

    it 'asks for the main channels when none is chosen' do
      [{}, { 'channels' => nil }, { 'channels' => [] }, { 'channels' => '' }].each do |fields|
        expect(requested(fields)).to eq(%w[TF1.fr France2.fr France3.fr CanalPlus.fr France5.fr M6.fr Arte.fr])
      end
    end

    it 'accepts the channels as a comma-separated string' do
      expect(requested('channels' => 'M6.fr, Arte.be')).to eq(%w[M6.fr Arte.be])
    end

    it 'reads a single channel, which TRMNL does not wrap' do
      rows = transformed('channels' => %w[Arte.be], 'mode' => 'tonight')['rows']
      expect(rows.map { it['name'] }).to eq(['Arte Belgique'])
    end
  end

  describe 'tonight' do
    it "picks the evening's first and second part, skipping the short programmes around 21:00" do
      rows = transformed('mode' => 'tonight')['rows'].to_h { [it['name'], [it['a']&.values_at('start', 'title'), it['b']&.values_at('start', 'title')]] }
      expect(rows['France 2']).to eq([['21:10', 'Au sein des autres'], ['22:40', 'Ce qui nous tient debout']])
      expect(rows['Arte']).to eq([['21:00', 'The Game'], ['23:00', 'Ring']])
      # Three episodes of Tracker in a row are one programme; the night filler is no second part.
      expect(rows['TF1']).to eq([['21:10', 'Tracker'], nil])
      # Not "Scènes de ménages" (20:40, 30 min).
      expect(rows['M6'].first).to eq(['21:10', 'La France a un incroyable talent'])
    end

    it 'keeps the order and the names of the chosen channels' do
      names = transformed('mode' => 'tonight', 'channels' => %w[Arte.fr TF1.fr LEquipe21.fr])['rows'].map { it['name'] }
      expect(names).to eq(['Arte', 'TF1', "L'Équipe"])
    end
  end

  describe 'now' do
    it 'shows the programme on now with its progress, and the next one' do
      out = transformed('mode' => 'now')
      expect(out['heading']).to eq('En ce moment')
      expect(out['rows'].size).to eq(7)
      out['rows'].each do |row|
        expect(row['a']['progress']).to be_between(0, 100)
        expect(row['b']['title']).not_to be_empty
      end
    end
  end

  it 'falls back to the main channels when none is chosen' do
    names = transformed('channels' => nil, 'mode' => 'tonight')['rows'].map { it['name'] }
    expect(names).to eq(['TF1', 'France 2', 'France 3', 'Canal+', 'France 5', 'M6', 'Arte'])
  end

  describe 'with 10 channels, the most a view shows' do
    let(:custom_fields) { { 'channels' => TNT.first(9) + %w[MaisonEtTravaux.fr] } }

    %w[full half_horizontal half_vertical quadrant].each do |view|
      it "draws the #{view} view without overlaps" do
        %w[og_plus v2].each do |device|
          [nil, :portrait].each do |orientation|
            %w[now tonight].each do |mode|
              args = { view:, device:, mocks:, custom_fields: custom_fields.merge('mode' => mode) }
              args[:orientation] = orientation if orientation
              screen = trmnl.render(**args)
              expect(screen).to have_no_problems.and(have_no_leaked_text).and(have_no_overlapping_text)
            end
          end
        end
      end
    end
  end
end
